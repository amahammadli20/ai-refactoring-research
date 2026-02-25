import functools
import json
import operator
import re
from pathlib import Path
from typing import Annotated, Sequence

import yaml
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

from compile_experiment import get_compile_result_in_commit
from model.refactoring_entity import RefactoringRepository

with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)
# OpenAI API key
OPENAI_API_KEY = config['OPENAI_API_KEY']
project_prefix_path = config['project_prefix_path']
project_name = config['project_name']
refactoring_map = RefactoringRepository.load_from_file(f"{project_prefix_path}/data/refactoring_info/refactoring_map_em_wc_v4.json",
                                                           format="json")
COMPILE_RESULT_FOR_REPAIR = False
REPAIRED_CODE = ""


file_path = f'{project_prefix_path}/data/{project_name}/{project_name}_evaluation_data.json'
project_path = f'{project_prefix_path}/projects/{project_name}'

with open(file_path, 'r') as file:
    data = json.load(file)

def create_agent(llm, tools, system_message: str):
    """Create an agent."""
    functions = [format_tool_to_openai_function(t) for t in tools]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful Program Repair AI assistant, collaborating with other assistants."
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


@tool
def get_buggy_code_by_bug_id(bug_id: str) -> str:
    """Get the buggy code by the bug id."""
    with open(f"{project_prefix_path}/data/bugs/{bug_id}_buggy_code.txt", 'r') as file:
        buggy_code = file.read()
    return buggy_code

@tool
def get_error_log_by_bug_id(bug_id: str) -> str:
    """Get the error log by the bug id."""
    with open(f"{project_prefix_path}/data/error_logs/{bug_id}_error_log.txt", 'r') as file:
        error_log = file.read()
    return error_log

@tool
def check_compile_result(bug_id: str, repaired_code: str) -> str:
    """Check the compile result of the repaired code."""
    global COMPILE_RESULT_FOR_REPAIR
    global REPAIRED_CODE
    REPAIRED_CODE = repaired_code
    print("call check_compile_result, bug_id: ", bug_id)
    lazy_code = check_lazy_code(repaired_code)
    if lazy_code:
        COMPILE_RESULT_FOR_REPAIR = False
        return "False, Please provide the complete code without omitting any parts."
    for refactoring in data:
        if refactoring['uniqueId'] == bug_id:
            file_path = project_path + "/" + refactoring['filePathBefore']
            compile_result, log = get_compile_result_in_commit(project_path, refactoring['commitId'], file_path, repaired_code)
            if compile_result:
                COMPILE_RESULT_FOR_REPAIR = True
                return "The repaired code compiles successfully."
            else:
                COMPILE_RESULT_FOR_REPAIR = False
                buggy_code_file_path = f"{project_prefix_path}/data/bugs/" + \
                                       bug_id + "_buggy_code.txt"
                buggy_code_file_path = Path(buggy_code_file_path)
                buggy_code_file_path.write_text(repaired_code, encoding="utf-8")
                error_log_file_path = f"{project_prefix_path}/data/error_logs/" + \
                                      bug_id + "_error_log.txt"
                error_log_file_path = Path(error_log_file_path)
                log = str(log)
                error_log_file_path.write_text(log, encoding="utf-8")
                return f"The repaired code does not compile successfully. The error log is as follows: {log}"
    COMPILE_RESULT_FOR_REPAIR = False
    return "cannot find the bug id"

repair_tools = [get_buggy_code_by_bug_id, get_error_log_by_bug_id]
reviewer_tools = [check_compile_result]

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




# create the OpenAI model
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=OPENAI_API_KEY)

# Research agent and node
repairer_agent = create_agent(
    llm,
    repair_tools,
    system_message="You are an repairer to fix buggy code. You should get the buggy code by `get_buggy_code_by_bug_id` based on the provided `bug_id`, you can use `get_error_log_by_bug_id` to get the error log of this buggy code. Please provide the complete code without omitting any parts. Do not abbreviate or truncate the code. You should output the whole java file content after fixing without omitting any code.",
)
repairer_node = functools.partial(agent_node, agent= repairer_agent, name="Repairer")

reviewer_agent = create_agent(
    llm,
    reviewer_tools,
    system_message="As a code review expert specializing in program repair, your role is to work closely with the Repairer, providing continuous feedback to make the code compile successfully. When reviewing the repaired code, no matter is before or after the update, you must use the `check_compile_result` to check the compile result. You don't need to repair this code, just give the comprehensive report to Repairer. The report should includes the compile result, and the error log of compile result, the position of buggy code. Do not write any other words in the report, just give the information to Repairer",
)
reviewer_node = functools.partial(agent_node, agent=reviewer_agent, name="Reviewer")

tools = repair_tools + reviewer_tools
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
    # This is the router
    messages = state["messages"]
    last_message = messages[-1]
    if "function_call" in last_message.additional_kwargs:
        # The previus agent is invoking a tool
        return "call_tool"
    if "FINAL ANSWER" in last_message.content:
        # Any agent decided the work is done
        return "end"
    # if "```json" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"
    # if "successfully completed" in last_message.content:
    #     # Any agent decided the work is done
    #     return "end"
    if "Great collaboration!" in last_message.content:
        # Any agent decided the work is done
        return "end"
    if "You're welcome!" in last_message.content:
        # Any agent decided the work is done
        return "end"
    return "continue"

workflow = StateGraph(AgentState)

workflow.add_node("Repairer", repairer_node)
workflow.add_node("Reviewer", reviewer_node)
workflow.add_node("call_tool", tool_node)

workflow.add_conditional_edges(
    "Repairer",
    router,
    {"continue": "Reviewer", "call_tool": "call_tool", "end": END},
)
workflow.add_conditional_edges(
    "Reviewer",
    router,
    {"continue": "Repairer", "call_tool": "call_tool", "end": END},
)

workflow.add_conditional_edges(
    "call_tool",
    # Each agent node updates the 'sender' field
    # the tool calling node does not, meaning
    # this edge will route back to the original agent
    # who invoked the tool
    lambda x: x["sender"],
    {
        "Repairer": "Repairer",
        "Reviewer": "Reviewer",
    },
)
workflow.add_edge(START, "Repairer")
graph = workflow.compile()

# Read the prompt
with open('data/prompts/repair_prompt.txt', 'r') as file:
    file_contents = file.read()

def add_result_to_refactoring(refactoring_id, answers):
    global REPAIRED_CODE
    global COMPILE_RESULT_FOR_REPAIR
    for refactoring in data:
        if refactoring['uniqueId'] == refactoring_id:
            answers_track = [answers[i]["messages"][0].content for i in range(len(answers))]
            refactoring['repairAgentChatLog'] = answers_track
            refactoring['repairRefactoredCode'] = REPAIRED_CODE
            refactoring['repairCompileAndTestResult'] = COMPILE_RESULT_FOR_REPAIR
            return refactoring

def extract_compile_and_test_result(answers_track):
    for answer in answers_track:
        if "check_compile_result response" in answer:
            return answer
    return "cannot find the refactoring result"

def extract_agent_refactored_code(answers_track):
    for answer in answers_track:
        code = extract_java_code(answer)
        if code:
            return code

def extract_java_code(agent_answer):
    pattern = re.compile(r'```java(.*?)```', re.DOTALL)
    matches = pattern.findall(agent_answer)
    return "\n".join(matches)

def extract_json(agent_answer):
    pattern = re.compile(r'```json(.*?)```', re.DOTALL)
    matches = pattern.findall(agent_answer)
    return "\n".join(matches)

def repair_code(bug_id):
    prompt2 = f"{file_contents.format(bug_id=bug_id)}"
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
                {"recursion_limit": 10},
        ):
            for key, value in s.items():
                print(f"Output from node '{key}':")
                print("---")
                print(value)
                # parse_and_save_json(value['messages'][0].content, project_name, bug_id)
                answers.append(value)
            print("\n---\n")
    except Exception as e:
        print(f"Error: {e}, bug_id: {bug_id}")
        return add_result_to_refactoring(bug_id, answers)
    return add_result_to_refactoring(bug_id, answers)

def check_lazy_code(refactored_code):
    if "other fields and methods remain unchanged" in refactored_code:
        return True
    return False
