from taipy.gui import Gui, notify

import re
import random
import pandas as pd
import requests

SECRET_PATH = "secret.txt"
with open(SECRET_PATH, "r") as f:
    API_TOKEN = f.read()

API_URL = "https://api-inference.huggingface.co/models/bigcode/starcoder"
headers = {"Authorization": f"Bearer {API_TOKEN}"}

CONTEXT_PATH = "context_data.csv"
LAYOUT_PATH = "layout_data.csv"
DATA_PATH = "sales_data_sample.csv"

context_data = pd.read_csv(CONTEXT_PATH, sep=";")
layout_data = pd.read_csv(LAYOUT_PATH, sep=";")
data = pd.read_csv(DATA_PATH, sep=",", encoding="ISO-8859-1")

data["ORDERDATE"] = pd.to_datetime(data["ORDERDATE"])
data = data.sort_values(by="ORDERDATE")

data_columns = data.columns.tolist()
context_columns = ["Sales", "Revenue", "Date", "Usage", "Energy"]

# Replace column names in the context with column names from the data
context = ""
for instruction, code in zip(context_data["instruction"], context_data["code"]):
    example = f"{instruction}\n{code}\n"
    for column in context_columns:
        example = example.replace(column, random.choice(data_columns))
    context += example

layout_context = ""
for instruction, code in zip(layout_data["instruction"], layout_data["code"]):
    example = f"{instruction}\n{code}\n"
    for column in context_columns:
        example = example.replace(column, random.choice(data_columns))
    layout_context += example


def query(payload: dict) -> dict:
    """
    Queries StarCoder API

    Args:
        payload: Payload for StarCoder API

    Returns:
        dict: StarCoder API response
    """
    response = requests.post(API_URL, headers=headers, json=payload, timeout=20)
    return response.json()


def plot_prompt(input_instruction: str) -> str:
    """
    Prompts StarCoder to generate Taipy GUI code

    Args:
        instuction (str): Instruction for StarCoder

    Returns:
        str: Taipy GUI code
    """
    current_prompt = f"{context}\n{input_instruction}\n"
    output = ""
    final_result = ""

    # Re-query until the output contains the closing tag
    timeout = 0
    while ">" not in output and timeout < 10:
        output = query(
            {
                "inputs": current_prompt + output,
                "parameters": {
                    "return_full_text": False,
                },
            }
        )[0]["generated_text"]
        timeout += 1
        final_result += output
    layout = layout_prompt(input_instruction)
    output_code = f"""<{final_result.split("<")[1].split(">")[0]}layout={layout}|>"""
    print(f"Plot code: {output_code}")

    # Check if the output code is valid
    pattern = r"<.*\|chart\|.*>"
    if bool(re.search(pattern, output_code)):
        return output_code
    else:
        raise Exception("Generated code is incorrect")


def layout_prompt(input_instruction: str) -> str:
    """
    Prompts StarCoder to generate Taipy GUI layout code

    Args:
        instuction (str): Instruction for StarCoder

    Returns:
        str: Taipy GUI layout code
    """
    current_prompt = f"{layout_context}\n{input_instruction}\n"
    output = ""
    final_result = ""

    # Re-query until the output contains the closing tag
    timeout = 0
    while "}" not in output and timeout < 5:
        output = query(
            {
                "inputs": current_prompt + output,
                "parameters": {
                    "return_full_text": False,
                },
            }
        )[0]["generated_text"]
        timeout += 1
        final_result += output
    # Keep everything before the last closing bracket
    output_code = final_result.split("}")
    output_code.pop()
    output_code = "}".join(output_code) + "}"
    print(f"Layout code: {output_code}")
    return output_code


def plot(state) -> None:
    """
    Prompt StarCoder to generate Taipy GUI code when user inputs plot instruction

    Args:
        state (State): Taipy GUI state
    """
    state.result = plot_prompt(state.plot_instruction)
    state.p.update_content(state, state.result)
    notify(state, "success", "Plot Updated!")


def on_exception(state, function_name: str, ex: Exception) -> None:
    """
    Catches exceptions and notifies user in Taipy GUI

    Args:
        state (State): Taipy GUI state
        function_name (str): Name of function where exception occured
        ex (Exception): Exception
    """
    notify(state, "error", f"An error occured in {function_name}: {ex}")


def modify_data(state) -> None:
    """
    Prompts StarCoder to generate pandas code to transform data

    Args:
        state (State): Taipy GUI state
    """
    current_prompt = f"def transfom(transformed_data: pd.DataFrame) -> pd.DataFrame:\n  # {state.data_instruction}\n  return "
    output = ""
    final_result = ""

    # Re-query until the output contains the closing tag
    timeout = 0
    while "\n" not in output and timeout < 10:
        output = query(
            {
                "inputs": current_prompt + output,
                "parameters": {
                    "return_full_text": False,
                },
            }
        )[0]["generated_text"]
        timeout += 1
        final_result += output
    final_result = final_result.split("\n")[0]

    if "groupby" in final_result and "reset_index" not in final_result:
        final_result = f"{final_result}.reset_index()"

    print(f"Data transformation code: {final_result}")
    try:
        state.transformed_data = pd.DataFrame(eval("state." + final_result))
        notify(state, "success", f"Data Updated with code:{final_result}")
    except Exception as ex:
        notify(state, "error", f"Error with code {final_result} --- {ex}")


def reset_data(state) -> None:
    """
    Resets transformed data to original data and resets plot

    Args:
        state (State): Taipy GUI state
    """
    state.transformed_data = state.data.copy()
    state.p.update_content(state, "")


transformed_data = data.copy()
data_instruction = ""
plot_instruction = ""
result = ""


page = """
# Taipy**Copilot**{: .color-primary}

<|Original Data|expandable|expanded=True|
<|{data}|table|width=100%|page_size=5|filter=True|>
|>

## Enter your instruction to **modify**{: .color-primary} data here:
**Example:** Sum SALES grouped by COUNTRY
<|{data_instruction}|input|on_action=modify_data|class_name=fullwidth|change_delay=1000|>

<|Reset Transformed Data|button|on_action=reset_data|>

<|Transformed Data|expandable|expanded=True|
<|{transformed_data}|table|width=100%|page_size=5|rebuild|filter=True|>
|>

## Enter your instruction to **plot**{: .color-primary} data here:
**Example:** Plot a pie chart of SALES by COUNTRY titled Sales by Country
<|{plot_instruction}|input|on_action=plot|class_name=fullwidth|change_delay=1000|>

<|part|partial={p}|>
"""

gui = Gui(page)
p = gui.add_partial(
    """<|{transformed_data}|chart|type=lines|x=ORDERDATE|y=SALES|layout={"xaxis": { "title": "temps" }}|>"""
)
gui.run()
