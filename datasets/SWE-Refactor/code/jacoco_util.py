import os
import re
import subprocess
import xml.etree.ElementTree as ET
from lxml import etree
from xml.dom import minidom


def run_command(command):
    """运行系统命令并捕获输出"""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    success = result.returncode == 0
    if success:
        print(f"Command succeeded: {command}")
    else:
        print(f"Command failed: {command}\n{result.stderr}")
    return success, result


def switch_java_version(version):
    """
    通过命令行切换 Java 版本。

    :param version: 要切换的 Java 版本（如 '17' 或 '11'）。
    :return: None
    """
    try:
        # 构建 jenv 切换命令

        command = ["jenv", "global", str(version)]

        # 执行命令
        subprocess.run(command, check=True)

        # 检查是否切换成功
        result = subprocess.run(["jenv", "version"], capture_output=True, text=True, check=True)
        if str(version) in result.stdout:
            print(f"成功切换到 Java {version}。")
        else:
            print(f"切换到 Java {version} 失败。当前版本: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"切换 Java 版本失败: {e}")
    except FileNotFoundError:
        print("未找到 jenv 命令，请确保 jenv 已正确安装并在路径中。")

def get_previous_commit(commit_id):
    """获取指定 commit 的上一个 commit"""
    result = subprocess.run(f"git rev-parse {commit_id}~1", shell=True, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print(f"Failed to get the previous commit for {commit_id}: {result.stderr}")
        return None

def switch_to_commit(commit_hash):
    """切换到指定的 Git commit"""
    try:
        subprocess.run(["git", "checkout", "-f", commit_hash], check=True)
        print(f"Switched to commit: {commit_hash}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to switch to commit {commit_hash}: {e}")
        return False


def is_test_method(class_file):
    """
    判断是否为测试方法，通过检查类文件路径是否包含 'test'。
    """
    return "/test/" in class_file.lower()


def remove_namespace(element):
    """
    移除 XML 中的命名空间
    """
    for elem in element.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]  # 去掉命名空间
    return element

def format_xml(element):
    """Format the XML for pretty-printing with custom indentation."""
    rough_string = ET.tostring(element, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")  # 2 spaces for indentation


def modify_build_file(project_dir):
    """修改构建文件，确保 JaCoCo 配置项正确"""
    if os.path.exists(os.path.join(project_dir, "build.gradle")):
        build_file_path = os.path.join(project_dir, "build.gradle")
        # if not os.path.exists(os.path.join(project_dir, "build.gradle")):
        # build_file_path = os.path.join(project_dir, "build.gradle.kts")
        with open(build_file_path, "r") as file:
            lines = file.readlines()

        has_plugins_block = any(line.strip().startswith("plugins {") for line in lines)
        has_jacoco_plugin = any("id 'jacoco'" in line for line in lines)
        print("has_plugins_block", has_plugins_block)
        print("has jacoco plugins", has_jacoco_plugin)

        if not has_plugins_block:
            with open(build_file_path, "a") as file:
                file.write("\nplugins {\n    id 'jacoco'\n}\n")
        elif not has_jacoco_plugin:
            for i, line in enumerate(lines):
                if line.strip().startswith("plugins {"):
                    print("insert ok")
                    lines.insert(i + 1, "    id 'jacoco'\n")
                    with open(build_file_path, "w") as file:
                        file.writelines(lines)
                    break
        jacoco_config = '''
jacoco {
    toolVersion = "0.8.12"
}

subprojects {
    apply plugin: 'jacoco'

    jacoco {
        toolVersion = "0.8.12"
    }

    tasks.withType(Test) {
        finalizedBy 'jacocoTestReport'
    }

    jacocoTestReport {
        dependsOn test

        reports {
            xml.required.set(true)
            html.required.set(true)
        }
    }
}
'''
        # with open(build_file_path, "a") as file:
        # file.write(jacoco_config)
        with open(build_file_path, "a") as file:
            file.write(
                "\njacocoTestReport {\n    dependsOn test\n    reports {\n        xml.required = true\n        html.required = true\n    }\n}\n")
        print(f"Updated {build_file_path} to include JaCoCo configuration.")
    elif os.path.exists(os.path.join(project_dir, "pom.xml")):
        print("Maven project detected. Skipping build file modification.")
        modify_pom_file(project_dir, os.path.join(project_dir, "pom.xml"))
    elif os.path.exists(os.path.join(project_dir, "build.gradle.kts")):
        build_file_path = os.path.join(project_dir, "build.gradle.kts")
        with open(build_file_path, "r") as file:
            lines = file.readlines()

        # 检查是否有 plugins 块
        has_plugins_block = any(line.strip().startswith("plugins {") for line in lines)

        # 如果没有 plugins 块，添加一个新的 plugins 块
        if not has_plugins_block:
            lines.insert(0, "plugins {\n    id(\"jacoco\")\n}\n")
        else:
            # 如果已有 plugins 块，检查是否有 jacoco 插件
            has_jacoco_plugin = any("id(\"jacoco\")" in line for line in lines)
            if not has_jacoco_plugin:
                for i, line in enumerate(lines):
                    if line.strip().startswith("plugins {"):
                        lines.insert(i + 1, '    id("jacoco")\n')
                        break

        # 添加 JaCoCo 配置块（如果没有配置过）
        jacoco_config = '''
jacoco {
    toolVersion = "0.8.12"
}

tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn(tasks.withType<Test>())

    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}
'''

        # 查找是否已经存在 jacoco 配置
        if not any("jacoco {" in line for line in lines):
            lines.append(jacoco_config)

        # 将修改后的内容写回到文件中
        with open(build_file_path, "w") as file:
            file.writelines(lines)

        print(f"Updated {build_file_path} to include JaCoCo configuration.")
        print("junit5 build file")
    else:
        print("Unsupported build system: No recognized build file found.")

def modify_pom_file(project_dir, pom_file):
    """修改 pom.xml，确保 JaCoCo 配置项正确"""
    parser = etree.XMLParser(remove_blank_text=True, strip_cdata=False, ns_clean=True)
    tree = etree.parse(pom_file, parser)
    root = tree.getroot()

    # 移除命名空间（如果有）
    for elem in root.xpath("//*"):
        elem.tag = etree.QName(elem).localname

    build = root.find("build")
    if build is None:
        build = etree.SubElement(root, "build")

    plugins = build.find("plugins")
    if plugins is None:
        plugins = etree.SubElement(build, "plugins")

    jacoco_plugin = None
    for plugin in plugins.findall("plugin"):
        artifact_id = plugin.find("artifactId")
        if artifact_id is not None and artifact_id.text == "jacoco-maven-plugin":
            jacoco_plugin = plugin
        if artifact_id is not None and artifact_id.text == "json-schema-validator":
            plugins.remove(plugin)
    jacoco_version = "0.8.12"  # 使用你希望的 JaCoCo 版本号
    if jacoco_plugin is None:
        jacoco_plugin = etree.SubElement(plugins, "plugin")
        etree.SubElement(jacoco_plugin, "groupId").text = "org.jacoco"
        etree.SubElement(jacoco_plugin, "artifactId").text = "jacoco-maven-plugin"
        etree.SubElement(jacoco_plugin, "version").text = jacoco_version  # 指定版本号
        executions = etree.SubElement(jacoco_plugin, "executions")
    else:
        version = jacoco_plugin.find("version")
        if version is None:
            etree.SubElement(jacoco_plugin, "version").text = jacoco_version  # 如果未指定，补充版本号
        executions = jacoco_plugin.find("executions")
        if executions is None:
            executions = etree.SubElement(jacoco_plugin, "executions")

    # 添加两个 execution 配置
    execution_ids = {exec_.find("id").text for exec_ in executions.findall("execution") if exec_.find("id") is not None}
    if "prepare-agent" not in execution_ids:
        prepare_exec = etree.SubElement(executions, "execution")
        etree.SubElement(prepare_exec, "id").text = "prepare-agent"
        prepare_goals = etree.SubElement(prepare_exec, "goals")
        etree.SubElement(prepare_goals, "goal").text = "prepare-agent"

    if "report" not in execution_ids:
        report_exec = etree.SubElement(executions, "execution")
        etree.SubElement(report_exec, "id").text = "report"
        etree.SubElement(report_exec, "phase").text = "package"
        report_goals = etree.SubElement(report_exec, "goals ")
        etree.SubElement(report_goals, "goal").text = "report"

    # 保留注释并写入文件
    with open(pom_file, "wb") as f:
        tree.write(f, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    # 执行 mvn tidy-pom
    run_mvn_tidy_pom(project_dir)


def run_maven_verify():
    """运行 mvn clean verify"""
    success, result = run_command("mvn clean package  -Drat.skip=true -Dmaven.javadoc.skip=true")
    str_result = ""
    if not success:
        # 打印构建失败的详细信息
        str_result = "\nBuild failed. Details:\n" + result.stdout + result.stderr
        ansi_escape = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]')
        str_result = ansi_escape.sub('', str_result)
        str_result = re.findall(r'\[ERROR\].*', str_result)
        print("\nBuild failed. Details:\n")
        print(result.stdout)  # 打印标准输出
        print("---------------------------------------------------------------line")
        print(result.stderr)  # 打印错误输出

    return success, str_result


def extract_method_coverage(class_name, method_name=None, class_file=None):
    """
    Extracts coverage information for a specific method in a given class from a JaCoCo XML report.

    Args:
        xml_file (str): Path to the JaCoCo XML report file.
        class_name (str): Fully qualified class name to extract coverage information for.
        method_name (str, optional): Method name to extract coverage information for. If None, extract all methods.

    Returns:
        dict: A dictionary where the keys are method names and values are their coverage details.
              Returns an empty dictionary if the class or method is not found.
    """
    # Find all JaCoCo XML files in the current directory and subdirectories
    jacoco_files = []
    for root_dir, _, files in os.walk("."):
        for file in files:
            if file == "jacoco.xml":
                jacoco_files.append(os.path.join(root_dir, file))

    if not jacoco_files:
        print("No JaCoCo XML files found in the current directory.")
        return {}
    print(f"Found {len(jacoco_files)} JaCoCo XML files.")
    print(jacoco_files)
    class_name = class_name.replace(".", "/")
    coverage_info = {}

    # Iterate through all found XML files
    for xml_path in jacoco_files:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Find the class element matching the specified class_name
            class_element = root.find(f".//class[@name='{class_name}']")
            if class_element is None:
                continue  # Move to the next XML file if class is not found

            methods = class_element.findall("method")
            for method in methods:
                if method_name and method.attrib["name"] != method_name:
                    continue  # Skip methods that don't match the specified name

                method_name_in_xml = method.attrib["name"]
                coverage_details = {}
                for counter in method.findall("counter"):
                    counter_type = counter.attrib["type"]
                    missed = int(counter.attrib["missed"])
                    covered = int(counter.attrib["covered"])
                    coverage_details[counter_type] = {"missed": missed, "covered": covered}

                coverage_info[method_name_in_xml] = coverage_details

            # Return if method is found
            if coverage_info:
                print(f"Coverage information found for {class_name}.{method_name} : {coverage_info}")
                return coverage_info

        except ET.ParseError as e:
            print(f"Error parsing {xml_path}: {e}")

    print(f"Coverage information not found for {class_name}.{method_name}")
    return coverage_info

def run_build_verify(project_dir):
    """动态判断构建工具并运行相应的构建命令"""
    if os.path.exists(os.path.join(project_dir, "build.gradle")):
        success, result = run_command("./gradlew clean build -x test")
    elif os.path.exists(os.path.join(project_dir, "pom.xml")):
        success, result = run_command("mvn clean package -Drat.skip=true -Dmaven.javadoc.skip=true")
    else:
        print("Unsupported build system: No recognized build file found.")
        return False, "Unsupported build system"

    str_result = ""
    if not success:
        # 打印构建失败的详细信息
        str_result = "\nBuild failed. Details:\n" + result.stdout + result.stderr
        ansi_escape = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]')
        str_result = ansi_escape.sub('', str_result)
        str_result = re.findall(r'\[ERROR\].*', str_result)
        print("\nBuild failed. Details:\n")
        print(result.stdout)  # 打印标准输出
        print("---------------------------------------------------------------line")
        print(result.stderr)  # 打印错误输出

    return success, str_result

def run_mvn_tidy_pom(project_dir):
    """
    Run the `mvn tidy:pom` command in the specified project directory.

    Args:
        project_dir (str): The path to the Maven project directory containing the pom.xml.

    Returns:
        str: The output from the command execution.
    """
    if not os.path.isdir(project_dir):
        raise ValueError(f"Invalid directory: {project_dir}")

    # Ensure pom.xml exists
    pom_path = os.path.join(project_dir, "pom.xml")
    if not os.path.isfile(pom_path):
        raise ValueError(f"No pom.xml found in the directory: {project_dir}")

    try:
        # Execute the Maven tidy command
        result = subprocess.run(
            ["mvn", "tidy:pom"],
            cwd=project_dir,
            text=True,
            capture_output=True,
            check=True
        )
        print("Maven tidy:pom executed successfully.")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error while running mvn tidy:pom: {e.stderr}")


def get_jacoco_result(project_dir, commit_hash, class_name, method_name, class_file, pom_file, java_version):

    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
        return


    previous_commit = get_previous_commit(commit_hash)
    # Step 1: 切换到指定 commit
    switch_result = switch_to_commit(previous_commit)
    if not switch_result:
        print(f"Failed to switch to commit {previous_commit}")
        return False, False, {"Switch Failed": {"missed": 0, "covered": 0}}
    coverage = None
    # Step 3: 修改 pom.xml
    modify_build_file(project_dir)
    # Step 4: 编译并生成覆盖率报告
    switch_java_version(java_version)
    verify_result, log = run_maven_verify()
    switch_java_version(17)
    if not verify_result:
        print(f"Failed to build the project: {log}")
        return False, False, {"Build Failed": {"missed": 0, "covered": 0}}
    # Step 2: 判断方法是否为测试方法
    if not is_test_method(class_file):
        coverage =  extract_method_coverage(class_name, method_name, class_file)
        # Step 5: 提取覆盖率信息
        if coverage:
            if coverage[method_name]["LINE"]["covered"] != 0:
                return True, True, coverage[method_name]
            else:
                return True, False, coverage[method_name]
        else:
            print(f"Coverage information not found for {class_name}.{method_name}")
            return True, False, {"Can't Find Information": {"missed": 0, "covered": 0}}
    else:
        print(f"The method {method_name} is a test method; skipping coverage extraction.")
        return True, True, {"testMethod": {"missed": 0, "covered": 1}}




if __name__ == "__main__":
    # 示例参数（可根据实际情况修改）
    commit_hash = "5e413ff0036dfb332340fc3fb85af57845906ded"
    class_name = "com.puppycrawl.tools.checkstyle.checks.metrics.BooleanExpressionComplexityCheck"
    method_name = "getDefaultTokens"
    class_file = "com/puppycrawl/tools/checkstyle/checks/metrics/BooleanExpressionComplexityCheck.java"
    pom_file = "./pom.xml"
    project_dir = "/Users/yisenxu/Downloads/Research/SOEN6491/Projects/llm-refactoring-miner/tmp/checkstyle"


    try:
        os.chdir(project_dir)
        print(f"Switched to project directory: {project_dir}")
    except Exception as e:
        print(f"Failed to switch to directory {project_dir}: {e}")
    get_jacoco_result(project_dir, commit_hash, class_name, method_name, class_file, pom_file)
