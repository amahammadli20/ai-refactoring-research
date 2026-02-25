import copy
import functools
import json
import operator
import os
import re
import subprocess
from pathlib import Path
from typing import Annotated, Sequence

import yaml
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.tools.render import format_tool_to_openai_function
from langchain_core.messages import (
    BaseMessage,
    FunctionMessage,
    HumanMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import END, StateGraph
from langgraph.prebuilt.tool_executor import ToolExecutor, ToolInvocation
from typing_extensions import TypedDict

from bm25 import BM25
from compile_experiment import get_compile_result_in_commit, switch_java_version
from rag.contextual_rag_process import get_context_description
from rag.rag_embedding import search_chroma
from rag.reciprocal_rank_fusion import ReciprocalRankFusion
from model.refactoring_entity import RefactoringRepository
from rag.reranking import Reranking
from workflow_for_fix_bug import repair_code
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)
# OpenAI API key
OPENAI_API_KEY = config['OPENAI_API_KEY']
project_prefix_path = config['project_prefix_path']
refactoring_map = RefactoringRepository.load_from_file(f"{project_prefix_path}/data/refactoring_info/refactoring_map_em_wc_v4.json",
                                                   format="json")
project_name = config['project_name']

file_path = f'{project_prefix_path}/data/{project_name}/{project_name}_evaluation_data.json'
project_path = f'{project_prefix_path}/projects/{project_name}'

COMPILE_COUNT = 0
CHECK_RE_COUNT = 0

REFACTORED_CODE = ""
COMPILE_RESULT = False
REFACTORING_RESULT = False
ERROR_LOG = ""
EXTRACT_METHOD = ""
REFACTORING_ID = ""

with open(file_path, 'r') as file:
    data = json.load(file)

def create_agent(llm, tools, system_message: str):
    """Create an agent."""
    functions = [format_tool_to_openai_function(t) for t in tools]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful Refactoring AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK, another assistant with different tools "
                " will help where you left off. Execute what you can to make progress."
                " If you don't communicate with the other assistants, please don't say FINAL ANSWER."
                " Only if you or any of the other assistants have the final answer or deliverable,"
                " prefix your final response with FINAL ANSWER so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
    return prompt | llm.bind_functions(functions)

def create_debugger_agent(llm, system_message: str):


    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "{system_message}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    prompt = prompt.partial(system_message=system_message)
    return prompt | llm


@tool
def get_similar_refactoring(source_code_before_refactoring: str, refactoring_type: str) -> list:
    """
    Get similar refactoring examples based on the source code before refactoring and refactoring type.
    """
    global REFACTORING_ID
    refactoring = get_refactoring(REFACTORING_ID)
    contextual_description = get_context_description(refactoring)
    print("call get_similar_refactoring, source_code_before_refactoring: ", source_code_before_refactoring,
          "refactoring_type: ", refactoring_type)
    bm25_model = BM25.load_model(
        f'{project_prefix_path}/data/model/refactoring_miner_em_wc_context_agent_collection_' + refactoring_type + '_bm25result.pkl')
    return get_historical_refactorings(contextual_description, refactoring_map, bm25_model, refactoring_type)

@tool
def get_method_body_by_refactoring_id(refactoring_id: str) -> str:
    """
    Get the method body by refactoring ID.
    """
    print("call get_method_body_by_refactoring_id, refactoring_id: ", refactoring_id)

    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            return refactoring['sourceCodeBeforeRefactoring']

@tool
def get_call_graph_by_refactoring_id(refactoring_id: str) -> str:
    """
    Get the call graph by refactoring ID.
    """
    print("call get_call_graph_by_refactoring_id, refactoring_id: ", refactoring_id)
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            if 'invokedMethod' not in refactoring:
                return "No call graph available."
            return refactoring['invokedMethod']




@tool
def check_java_style(refactoring_id: str, refactored_code: str, refactoring_json:str = "") -> str:
    """Input: refactoring_id, refactored_code, refactoring_json. Function: Check the Java code style using Checkstyle."""
    config_file = f"{project_prefix_path}/data/config/sun_checks.xml"
    file_path = f"{project_prefix_path}/data/tmp/TempClass.java"
    print("call check_java_style")

    global REFACTORED_CODE
    global EXTRACT_METHOD

    if refactoring_json != "":
        extract_method_full = refactoring_json.split('target_file_path')[0]
        extract_method_code_list = extract_method_full.split('extract_method_code')
        if len(extract_method_code_list) >= 1:
            extract_method_code = extract_method_code_list[1]
        if extract_method_code != "":
            EXTRACT_METHOD = extract_method_code
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            code_before_refactoring = refactoring['sourceCodeBeforeRefactoring']
            code_before_refactoring_for_whole = refactoring['sourceCodeBeforeForWhole']
            refactored_code = code_before_refactoring_for_whole.replace(code_before_refactoring, refactored_code)
            REFACTORED_CODE = refactored_code
            file_path = Path(file_path)
            file_path.write_text(refactored_code, encoding="utf-8")
            result = subprocess.run(
                ["java", "-jar",
                 f"{project_prefix_path}/data/tools/checkstyle-10.20.1-all.jar",
                 "-c", config_file, str(file_path)],
                capture_output=True,
                text=True
            )
            style_result = result.stdout
            lines = style_result.strip().splitlines()
            error_lines = lines[2:] if len(lines) > 2 else []
            error_descriptions = []
            pattern = re.compile(r':(\d+):(\d+): (.*? \[.*?\].*?)')
            for line in error_lines:
                match = pattern.search(line)
                if match:
                    line_number = int(match.group(1)) - 4
                    column_number = match.group(2)
                    message = match.group(3)
                    result = f"line:{line_number} column:{column_number}: {message}"
                    error_descriptions.append(result)
            return "\n".join(error_descriptions)

    return "False, the refactoring id is not found."
@tool
def check_refactoring_result(refactoring_id: str, refactored_code: str, refactoring_json: str = ""):
    """ Input: refactored_code, refactored_code, and refactoring_json. Function: Check if the code is actually refactored"""
    global REFACTORING_RESULT
    global REFACTORED_CODE
    global EXTRACT_METHOD

    # if refactoring_json == "":
    #     return "False, Please provide the refactoring_json parameter."
    # extract_method_full = refactoring_json.split('target_file_path')[0]
    # extract_method_code_list = extract_method_full.split('extract_method_code')
    # if len(extract_method_code_list) >= 1:
    #     extract_method_code = extract_method_code_list[1]
    # if extract_method_code != "":
    #     EXTRACT_METHOD = extract_method_code
    print("call check_refactoring_result, refactoring_id:", refactoring_id)
    refactoring_type = ""
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            code_before_refactoring = refactoring['sourceCodeBeforeRefactoring']
            code_before_refactoring_for_whole = refactoring['sourceCodeBeforeForWhole']
            refactored_code = code_before_refactoring_for_whole.replace(code_before_refactoring, refactored_code)
            REFACTORED_CODE = refactored_code
            refactoring_type = refactoring['type']
            if refactoring_type == "Move Method" or refactoring_type == "Move And Rename Method":
                return check_move_method_refactoring(refactoring, refactored_code, refactoring_json)
            if refactoring_type == "Extract And Move Method":
                return check_extraction_and_move_method_refactoring(refactoring, refactored_code, refactoring_json)
            if refactoring_type == "Move And Inline Method":
                return check_move_and_inline_method_refactoring(refactoring, refactored_code, refactoring_json)
            return check_extraction_refactoring(refactoring, refactored_code, refactoring_type)
    REFACTORING_RESULT = False
    return False, "the code didn't perform "+ refactoring_type + " operation."

def check_refactoring_result_with_context(refactoring_id: str, refactored_code: str, refactoring_json: str = ""):
    global REFACTORING_RESULT
    global REFACTORED_CODE
    global EXTRACT_METHOD

    refactoring_type = ""
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            code_before_refactoring = refactoring['sourceCodeBeforeRefactoring']
            code_before_refactoring_for_whole = refactoring['sourceCodeBeforeForWhole']
            refactored_code = code_before_refactoring_for_whole.replace(code_before_refactoring, refactored_code)
            REFACTORED_CODE = refactored_code
            refactoring_type = refactoring['type']
            if refactoring_type == "Move Method" or refactoring_type == "Move And Rename Method":
                return check_move_method_refactoring(refactoring, refactored_code, refactoring_json)
            if refactoring_type == "Extract And Move Method":
                return check_extraction_and_move_method_refactoring(refactoring, refactored_code, refactoring_json)
            if refactoring_type == "Move And Inline Method":
                return check_move_and_inline_method_refactoring(refactoring, refactored_code, refactoring_json)
            return check_extraction_refactoring(refactoring, refactored_code, refactoring_type)
    REFACTORING_RESULT = False
    return False, "the code didn't perform "+ refactoring_type + " operation."

def check_extraction_and_move_method_refactoring(refactoring, refactored_class_code, refactoring_json):
    global REFACTORING_RESULT
    result, message = check_extraction_refactoring(refactoring, refactored_class_code, "Extract Method")
    move_result, move_message =  check_move_method_refactoring(refactoring, refactored_class_code, refactoring_json)
    REFACTORING_RESULT = result and move_result
    return result and move_result, message + " " + move_message

def check_extraction_refactoring(refactoring, refactored_class_code, refactoring_type):
    global REFACTORING_RESULT
    source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
    file_path_before = f"{project_prefix_path}/data/tmp/source_code_before_for_whole.txt"
    file_path_after = f"{project_prefix_path}/data/tmp/source_code_after_for_whole.txt"
    with open(file_path_before, "w", encoding="utf-8") as file:
        file.write(source_code_before_for_whole)
    with open(file_path_after, "w", encoding="utf-8") as file:
        file.write(refactored_class_code)
    java_file_path = refactoring['filePathBefore']
    try:
        os.chdir(project_prefix_path)
        print(f"Switched to project directory: {project_path}")
    except Exception as e:
        print(f"Failed to switch to directory {project_path}: {e}")
    switch_java_version(17)
    exe_result = subprocess.run(
        ["./data/tools/RefactoringMiner-3.0.10/bin/RefactoringMiner", "-scr", java_file_path, file_path_before,
         file_path_after, refactoring_type], capture_output=True, text=True)
    refactoring_result = exe_result.stdout
    last_line = refactoring_result.strip().split('\n')[-1]
    result_word = [word for word in last_line.split()]
    if result_word[0] == "true":
        REFACTORING_RESULT = True
        return True, " the " + refactoring_type +" operation is successful."
    else:
        REFACTORING_RESULT = False
        return False, " the code didn't perform " + refactoring_type +" operation."

def check_move_and_inline_method_refactoring(refactoring, refactored_class_code, refactoring_json):
    global REFACTORING_RESULT
    target_file_path = ""
    try:
        move_method_refactoring = json.loads(refactoring_json, strict=False)
        target_file_path = move_method_refactoring['target_file_path']
    except Exception as e:
        print("Json load Error: ", e)
    if target_file_path == "":
        REFACTORING_RESULT = False
        return False, "the target file path is empty, please move to an existing java file."
    full_file_path = project_path + "/" + target_file_path
    if not os.path.exists(full_file_path):
        REFACTORING_RESULT = False
        return False, " this is a new file, please move to an existing java file."
    with open(full_file_path, "r", encoding="utf-8") as file:
        target_class_code = file.read()
    method_name_before = refactoring['methodNameBefore'].split("#")[1]
    if method_name_before not in target_class_code:
        REFACTORING_RESULT = False
        return False, " the call of move method is not in the target class."
    REFACTORING_RESULT = True
    return True, "the move and inline method operation is successful."

def check_move_method_refactoring(refactoring, refactored_class_code, refactoring_json):
    global REFACTORING_RESULT
    target_file_path = ""
    try:
        move_method_refactoring = json.loads(refactoring_json, strict = False)
        target_file_path = move_method_refactoring['target_file_path']
    except Exception as e:
        print("Json load Error: ", e)
    print("target_file_path: ", target_file_path)
    if target_file_path == "":
        REFACTORING_RESULT = False
        return False, "the target file path is empty, please move to an existing java file."
    full_file_path = project_path + "/" + target_file_path
    if not os.path.exists(full_file_path):
        REFACTORING_RESULT = False
        return False, " this is a new file, please move to an existing java file."
    REFACTORING_RESULT = True
    return True, "the move method operation is successful."



@tool
def check_pure_refactoring_result(refactoring_id: str, refactored_class_code: str):
    """ Check whether pure refactoring is performed"""
    print("call check_pure_refactoring_result, refactoring_id: ", refactoring_id)
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            source_code_before_for_whole = refactoring['sourceCodeBeforeForWhole']
            file_path_before = f"{project_prefix_path}/data/tmp/source_code_before_for_whole.txt"
            file_path_after = f"{project_prefix_path}/data/tmp/source_code_after_for_whole.txt"
            with open(file_path_before, "w", encoding="utf-8") as file:
                file.write(source_code_before_for_whole)
            with open(file_path_after, "w", encoding="utf-8") as file:
                file.write(refactored_class_code)
            java_file_path = refactoring['filePathBefore']
            exe_result = subprocess.run(
                ["./data/tools/RefactoringMiner-3.0.10/bin/RefactoringMiner", "-scr", java_file_path,
                 file_path_before, file_path_after], capture_output=True, text=True)
            refactoring_result = exe_result.stdout
            last_line = refactoring_result.strip().split('\n')[-1]
            result_word = [word for word in last_line.split()]
            if result_word[1] == "true":
                return "True, the refactoring operation is successful. And the" + refactoring['type'] + "is pure refactoring."
    return "False, the refactoring is not pure refactoring."





@tool
def get_refactoring_operation_by_refactoring_id(refactoring_id: str) -> str:
    """Get the refactoring operation by refactoring ID."""
    print("call get_refactoring_operation_by_refactoring_id, refactoring_id: ", refactoring_id)
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            return refactoring['type']

@tool
def check_compile_result(refactoring_id: str, refactored_code: str, refactoring_json: str = "") -> str:
    """Input: refactoring_id, refactored_code, and refactoring_json. Function: Check the compile result of the refactored code."""

    global COMPILE_RESULT
    global REFACTORING_RESULT
    global REFACTORED_CODE
    global ERROR_LOG
    print("call check_compile_result, refactoring_id: ", refactoring_id)
    refactoring_log = ""
    if not REFACTORING_RESULT:
        refactoring_result, refactoring_log = check_refactoring_result_with_context(refactoring_id, refactored_code, refactoring_json)
        refactoring_log = "\nCheck Refactoring Result:" + refactoring_log
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            code_before_refactoring = refactoring['sourceCodeBeforeRefactoring']
            code_before_refactoring_for_whole = refactoring['sourceCodeBeforeForWhole']
            refactored_code = code_before_refactoring_for_whole.replace(code_before_refactoring, refactored_code)
            REFACTORED_CODE = refactored_code
            if refactoring['type'] == "Move Method" or refactoring['type'] == "Move And Rename Method" or refactoring['type'] == "Move And Inline Method":
                return check_move_method_compile_result(refactoring, refactored_code, refactoring_json) + refactoring_log
            if refactoring['type'] == "Extract And Move Method":
                return check_extraction_and_move_method_compile_result(refactoring, refactored_code, refactoring_json) + refactoring_log
            file_path = project_path + "/" + refactoring['filePathBefore']
            java_version = refactoring['compileJDK']
            compile_result, log = get_compile_result_in_commit(project_path, refactoring['commitId'], file_path, refactored_code, java_version)
            if compile_result:
                COMPILE_RESULT = True
                ERROR_LOG = ""
                return "The refactored code compiles successfully." + refactoring_log
            else:
                COMPILE_RESULT = False
                ERROR_LOG = log
                return f"The refactored code does not compile successfully. The error log is as follows: {log}" + refactoring_log
    COMPILE_RESULT = False
    ERROR_LOG = "cannot find the refactoring id"
    return "cannot find the refactoring id" + refactoring_log

def check_extraction_and_move_method_compile_result(refactoring, refactored_class_code, refactoring_json):
    global COMPILE_RESULT
    global ERROR_LOG
    file_path = project_path + "/" + refactoring['filePathBefore']
    compile_result, log = get_compile_result_in_commit(project_path, refactoring['commitId'], file_path,
                                                       refactored_class_code)
    if compile_result:
        COMPILE_RESULT = True
        ERROR_LOG = ""
        result = "The refactored code compiles successfully."
        result = result + " " + check_move_method_compile_result(refactoring, refactored_class_code, refactoring_json)
        return result
    else:
        COMPILE_RESULT = False
        ERROR_LOG = log
        return f"The refactored code does not compile successfully. The error log is as follows: {log}"


def check_move_method_compile_result(refactoring, refactored_class_code, refactoring_json):
    global COMPILE_RESULT
    global ERROR_LOG
    target_file_path = ""
    try:
        move_method_refactoring = json.loads(refactoring_json, strict=False)
        target_file_path = move_method_refactoring['target_file_path']
    except Exception as e:
        print("Json load Error: ", e)
    if target_file_path == "":
        COMPILE_RESULT = False
        ERROR_LOG = "False, the target file path is empty, please move to an existing java file."
        return "False, the target file path is empty, please move to an existing java file."
    full_file_path = project_path + "/" + target_file_path
    if not os.path.exists(full_file_path):
        COMPILE_RESULT = False
        ERROR_LOG = "False, this is a new file, please move to an existing java file."
        return "False, The target file path does not exist, please move to an existing java file."
    COMPILE_RESULT = True
    ERROR_LOG = ""
    return "True, the move method operation is successful. The refactored code compiles successfully."

def get_historical_refactorings(search_text, refactoring_map, bm25_model, refactoring_type):
    # get embedding search result
    embedding_result = search_chroma(search_text, n_results=10, collection_name='refactoring_miner_em_wc_context_agent_collection', refactoring_type=refactoring_type)
    embedding_document = embedding_result['documents'][0]
    # get BM25 search result
    bm25_document = bm25_model.search(search_text, top_n=10)
    # reciprocal rank fusion
    ranked_lists = [embedding_document, bm25_document]
    rrf = ReciprocalRankFusion(k=60)

    scores = rrf.fuse(ranked_lists)

    # Get the top 10 documents
    top_docs = rrf.get_top_n(scores, n=10)

    top_docs_text = [doc[0] for doc in top_docs]
    # Reranking the top 10 documents
    reranker = Reranking("colbert")
    query = search_text
    ranked_results = reranker.rerank(query, top_docs_text)
    top_ranked_result = ranked_results.top_k(1)
    metadata_refactoring = []
    for result in top_ranked_result:
        metadata_refactoring.append(refactoring_map[result.document.text])
    search_result = "\n".join([
        f"Example {i + 1}:\n Refactoring Description:\n {example['description']}\n SourceCodeBeforeRefactoring:\n {example['sourceCodeBeforeRefactoring']}\n filePathBefore:\n {example['filePathBefore']}\n SourceCodeAfterRefactoring:\n {example['sourceCodeAfterRefactoring']}"
        for i, example in enumerate(metadata_refactoring)
    ])
    return search_result

def get_refactoring_type(refactoring_id):
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            return refactoring['type']

refactoring_tools = [get_refactoring_operation_by_refactoring_id, get_similar_refactoring, get_call_graph_by_refactoring_id, get_method_body_by_refactoring_id]
reviewer_tools = [check_compile_result, check_refactoring_result, check_java_style]

# This defines the object that is passed between each node
# in the graph. We will create different nodes for each agent and tool
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    sender: str


# Helper function to create a node for a given agent
def agent_node(state, agent, name):
    result = agent.invoke(state)
    # We convert the agent output into a format that is suitable to append to the global state
    if isinstance(result, FunctionMessage):
        pass
    else:
        result = HumanMessage(**result.dict(exclude={"type", "name"}), name=name)
    return {
        "messages": [result],
        # Since we have a strict workflow, we can
        # track the sender so we know who to pass to next.
        "sender": name,
    }


# 创建一个LangChain模型
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=OPENAI_API_KEY)
# llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0, openai_api_key=OPENAI_API_KEY)


# Research agent and node
developer_agent = create_agent(
    llm,
    refactoring_tools,
    system_message="You are a developer to refactoring. You should refactor the code retrieved from `get_method_body_by_refactoring_id` based on the provided `refactoring_id`.  During the refactoring process, You need to first use `get_refactoring_operation_by_refactoring_id` to get refactoring operation, and then use get_similar_refactoring to obtain the most similar refactoring example for reference according to source code and operation type. Please provide the refactored method code and extracted method code. You should output the refactored code and a json file contains the `extract_method_code` and `target_file_path` for extract and move operation. If you perform extract method, the extracted method should save in the `extract_method_code` field of the json file. If the code need to be moved to another class, you should output the path of the target class, i.e. `target_file_path` and the refactored code will be the entire class code for the target class. The ultimate goal is to produce executable refactored code.",
)
developer_node = functools.partial(agent_node, agent= developer_agent, name="Developer")

reviewer_agent = create_agent(
    llm,
    reviewer_tools,
    system_message="As a code review expert specializing in refactoring, your role is to work closely with the developer, providing continuous feedback to enhance code quality. When reviewing the refactored code, no matter is before or after the update, you must use the `check_compile_result` to check the compile result, the `check_refactoring_result` tool to verify that refactoring was indeed applied, `check_java_style` to assess adherence to Java style guidelines. Checking the refactoring result is the most important thing to ensure that the refactoring operation is successful, you must keep the refactoring perform successfully. You don't need to refactoring this code, just give the comprehensive report to developer. You cannot give a feedback report without executing these three tools. The report should includes, the compile result, refactoring result, the style issue, and the error log of compile result, the position of buggy code. Do not write any other words in the report, just give the information to Developer.",
)
reviewer_node = functools.partial(agent_node, agent=reviewer_agent, name="Reviewer")


tools = refactoring_tools + reviewer_tools
tool_executor = ToolExecutor(tools)

def tool_node(state):
    """This runs tools in the graph

    It takes in an agent action and calls that tool and returns the result."""
    messages = state["messages"]
    # Based on the continue condition
    # we know the last message involves a function call
    last_message = messages[-1]
    # We construct an ToolInvocation from the function_call
    tool_input = json.loads(
        last_message.additional_kwargs["function_call"]["arguments"]
    )
    # We can pass single-arg inputs by value
    if len(tool_input) == 1 and "__arg1" in tool_input:
        tool_input = next(iter(tool_input.values()))
    tool_name = last_message.additional_kwargs["function_call"]["name"]
    action = ToolInvocation(
        tool=tool_name,
        tool_input=tool_input,
    )
    # We call the tool_executor and get back a response
    response = tool_executor.invoke(action)
    # We use the response to create a FunctionMessage
    function_message = FunctionMessage(
        content=f"{tool_name} response: {str(response)}", name=action.tool
    )
    # We return a list, because this will get added to the existing list
    return {"messages": [function_message]}

# Either agent can decide to end
def router(state):
    global COMPILE_RESULT
    global REFACTORING_RESULT
    # This is the router
    global COMPILE_COUNT
    messages = state["messages"]
    last_message = messages[-1]
    if "function_call" in last_message.additional_kwargs:
        # The previus agent is invoking a tool
        return "call_tool"
    if COMPILE_RESULT and REFACTORING_RESULT:
        # Any agent decided the work is done
        return "end"
    # if "```json" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"
    # if "successfully completed" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"
    # if "Great collaboration" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"
    #
    # if "You're welcome!" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"

    return "continue"

def reviewer_router(state):
    # This is the router
    global COMPILE_COUNT
    global CHECK_RE_COUNT
    messages = state["messages"]
    last_message = messages[-1]
    if "function_call" in last_message.additional_kwargs:
        # The previus agent is invoking a tool
        if "name" in last_message.additional_kwargs["function_call"]:
            call_name = last_message.additional_kwargs["function_call"]["name"]
            if call_name == "check_compile_result":
                if COMPILE_COUNT >= 2:
                    COMPILE_COUNT =0
                    return "continue"
                COMPILE_COUNT = COMPILE_COUNT + 1
            if call_name == "check_refactoring_result":
                if CHECK_RE_COUNT >= 2:
                    CHECK_RE_COUNT = 0
                    return "continue"
                CHECK_RE_COUNT = CHECK_RE_COUNT + 1
        return "call_tool"
    if COMPILE_RESULT and REFACTORING_RESULT:
        # Any agent decided the work is done
        return "end"
        # Any agent decided the work is done
    return "continue"
workflow = StateGraph(AgentState)

workflow.add_node("Developer", developer_node)
workflow.add_node("Reviewer", reviewer_node)
workflow.add_node("call_tool", tool_node)

workflow.add_conditional_edges(
    "Developer",
    router,
    {"continue": "Reviewer", "call_tool": "call_tool", "end": END},
)
workflow.add_conditional_edges(
    "Reviewer",
    reviewer_router,
    {"continue": "Developer", "call_tool": "call_tool", "end": END},
)

workflow.add_conditional_edges(
    "call_tool",
    # Each agent node updates the 'sender' field
    # the tool calling node does not, meaning
    # this edge will route back to the original agent
    # who invoked the tool
    lambda x: x["sender"],
    {
        "Developer": "Developer",
        "Reviewer": "Reviewer",
    },
)
workflow.add_edge(START, "Developer")
graph = workflow.compile()



test_id_schema = ResponseSchema(name="refactoring_id",
                             description="The id of the refactoring")

refactoring_id_schema = ResponseSchema(name="refactoring_id",
                             description="The id of the refactoring")

refactored_code_list_schema = ResponseSchema(name="refactored_code",
                                      description="The potential refactored code in a list")


response_schemas = [refactoring_id_schema, refactored_code_list_schema]

output_parser2 = StructuredOutputParser.from_response_schemas(response_schemas)
format_instructions_methodsig = output_parser2.get_format_instructions()

# Read the prompt
with open('data/prompts/refactoring_prompt_util.txt', 'r') as file:
    file_contents = file.read()

def get_refactoring_ids_from_json(start, end):
    refactoring_ids = []
    count = 0
    for refactoring in data:
        if start <= count < end:
            refactoring_ids.append(refactoring['uniqueId'])
        count += 1
    return refactoring_ids

def get_refactoring_ids_from_txt(file_path, start, end):
    refactoring_ids = []
    count = 0
    with open(file_path, 'r') as file:
        for line in file:
            if start <= count < end:
                refactoring_ids.append(line.strip())
            count += 1
    return refactoring_ids

def add_result_to_refactoring(refactoring_id, answers):
    global REFACTORED_CODE
    global REFACTORING_RESULT
    global COMPILE_RESULT
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            answers_track = [answers[i]["messages"][0].content for i in range(len(answers))]
            refactoring['agentChatLog'] = answers_track
            refactoring['refactoringMinerResult'] = REFACTORING_RESULT
            refactoring['agentRefactoredCode'] = REFACTORED_CODE
            refactoring['compileAndTestResult'] = COMPILE_RESULT
            return refactoring

def refactor_code(refactoring_id, prompt2):
    answers = []
    try:
        for s in graph.stream(
                {
                    "messages": [
                        HumanMessage(
                            content=prompt2
                        )
                    ],
                },
                # Maximum number of steps to take in the graph
                {"recursion_limit": 50},
        ):
            for key, value in s.items():
                print(f"Output from node '{key}':")
                print("---")
                print(value)
                # parse_and_save_json(value['messages'][0].content, project_name, bug_id)
                answers.append(value)
            print("\n---\n")
    except Exception as e:
        print(f"Error: {e}, refactoring_id: {refactoring_id}")
        return add_result_to_refactoring(refactoring_id, answers)
    return add_result_to_refactoring(refactoring_id, answers)

def check_lazy_code(refactored_code):
    if "other fields and methods remain unchanged" in refactored_code:
        return True
    if "// Other test methods..." in refactored_code:
        return True
    return False

def perform_repair(refactoring_for_repair):
    global ERROR_LOG
    compile_result = refactoring_for_repair['compileAndTestResult']
    if not compile_result:
        buggy_code = refactoring_for_repair['agentRefactoredCode']
        error_log = str(ERROR_LOG)
        buggy_code_file_path = f"{project_prefix_path}/data/bugs/" + refactoring_for_repair['uniqueId'] + "_buggy_code.txt"
        buggy_code_file_path = Path(buggy_code_file_path)
        buggy_code_file_path.write_text(buggy_code, encoding="utf-8")
        error_log_file_path = f"{project_prefix_path}/data/error_logs/" + refactoring_for_repair['uniqueId'] + "_error_log.txt"
        error_log_file_path = Path(error_log_file_path)
        error_log_file_path.write_text(error_log, encoding="utf-8")
        repaired_code = repair_code(refactoring_for_repair['uniqueId'])
        if repaired_code is not None:
            refactoring_for_repair['repairRefactoredCode'] = repaired_code['repairRefactoredCode']
            refactoring_for_repair['repairCompileAndTestResult'] = repaired_code['repairCompileAndTestResult']
            return refactoring_for_repair
        refactoring_for_repair['repairRefactoredCode'] = ""
        refactoring_for_repair['repairCompileAndTestResult'] = False
        return refactoring_for_repair
    return refactoring_for_repair

def set_refactoring_type(refactoring_id, refactoring_type):
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            # 1. first perform extract method refactoring
            refactoring['type'] = refactoring_type

def get_refactoring(refactoring_id):
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            return refactoring

def get_after_move_refactoring(refactoring_id, refactoring_result, refactoring_code):
    global EXTRACT_METHOD
    refactoring_before = get_refactoring(refactoring_id)
    refactoring_for_move = copy.deepcopy(refactoring_before)
    refactoring_for_move['type'] = "Move Method"
    refactoring_for_move['sourceCodeBeforeForWhole'] = refactoring_result[refactoring_code]
    refactoring_for_move['uniqueId'] = refactoring_id + "_move"
    refactoring_for_move['sourceCodeBeforeRefactoring'] = EXTRACT_METHOD
    refactoring_for_move['methodNameBefore'] = ""
    data.append(refactoring_for_move)
    prompt2 = f"{file_contents.format(refactoring_id=refactoring_for_move['uniqueId'])}"
    refactoring_result_after_move = refactor_code(refactoring_for_move['uniqueId'], prompt2)
    return refactoring_result_after_move

def handle_extract_and_move_method(refactoring_id, prompt2):
    set_refactoring_type(refactoring_id, "Extract Method")
    refactoring_result = refactor_code(refactoring_id, prompt2)
    if refactoring_result['refactoringMinerResult'] and not refactoring_result['compileAndTestResult']:
        refactoring_result = perform_repair(refactoring_result)
        if refactoring_result['repairCompileAndTestResult']:
            refactoring_result_after_move = get_after_move_refactoring(refactoring_id, refactoring_result, 'repairRefactoredCode')
            refactoring_result['moveMethodResult'] = refactoring_result_after_move
            refactoring_result['moveMethodResultRefactoringMiner'] = refactoring_result_after_move['refactoringMinerResult']
            return refactoring_result
    elif refactoring_result['refactoringMinerResult'] and refactoring_result['compileAndTestResult']:
        refactoring_result_after_move = get_after_move_refactoring(refactoring_id, refactoring_result,'agentRefactoredCode')
        refactoring_result['moveMethodResult'] = refactoring_result_after_move
        refactoring_result['moveMethodResultRefactoringMiner'] = refactoring_result_after_move['refactoringMinerResult']
        return refactoring_result
    return refactoring_result


def remove_java_comments(java_code):
    pattern = r"(//.*?$|/\*.*?\*/|/\*\*.*?\*/)"
    cleaned_code = re.sub(pattern, '', java_code, flags=re.DOTALL | re.MULTILINE)
    return cleaned_code

def extract_method_util(refactoring_id, is_extract_and_move = False):
    global REFACTORING_RESULT
    global COMPILE_RESULT
    global EXTRACT_METHOD
    global REFACTORING_ID
    REFACTORING_RESULT = False
    COMPILE_RESULT = False
    REFACTORING_ID = refactoring_id
    if is_extract_and_move:
        set_refactoring_type(refactoring_id, "Extract Method")
    prompt2 = f"{file_contents.format(refactoring_id=refactoring_id)}"
    refactoring_result = refactor_code(refactoring_id, prompt2)
    if is_extract_and_move:
        refactoring_result['extractMethodCode'] = EXTRACT_METHOD
    if refactoring_result['refactoringMinerResult'] and not refactoring_result['compileAndTestResult']:
        refactoring_result = perform_repair(refactoring_result)
    return refactoring_result

