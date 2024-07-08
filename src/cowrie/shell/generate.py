#!/bin/bash

# bin/cowrie generate src/cowrie/shell/generate.py <input cmd> <args/optional>
from __future__ import annotations

from openai import OpenAI
import sys
import shutil
import os

def add_context(prompt_filepath:str, cmd: str, msg: str):
    # write context for single cmd input into prompt file
    with open(prompt_filepath, 'a+') as f:
        f.write("This was the previous Linux command input by the user and your generated output. You must use this as context for the same subsequent commands.\n")
        f.write(f"root@svr04:~# {cmd}\n")
        f.write(msg)
        f.write("\n")
    f.close()

def gen_cmdOutput(input_cmd: str, args: str) -> None:
    # generate any long command outputs here
    has_args = False
    call_count = 4
    prompt_filepath = f"./src/cowrie/shell/shelLM/{input_cmd}_prompt.txt"
    print(input_cmd, args)

    client = OpenAI(api_key='your api key')

    if len(args) == 0:
        cmd = input_cmd
    else:
        cmd = input_cmd + " " + args
        has_args = True
    print(cmd)
    
    initial_prompt = f"You are a Linux OS terminal. Your task is to respond exactly as a Linux terminal would. The user has input this Linux command {cmd}. \
            Use the information provided as a reference and generate the output accordingly."
    prompt = "You must not act like a chatbot. \
            You must not explain any inputs or outputs. \
            You must not in any case have a conversation with user as a chatbot and must not explain your output and do not repeat commands user inputs."
    
    with open(prompt_filepath, 'r') as pFile:
        personality_prompt = pFile.read()

    message = [{"role": "system", "content": initial_prompt+personality_prompt+prompt}]
    response = client.chat.completions.create( 
        model="gpt-3.5-turbo",
        messages = message,
        temperature = 0.1
    )
    res = response.choices[0].message.content

    out_name = f"{cmd}.txt" 
    out_filepath = f"./src/cowrie/shell/cache_out/{out_name}"

    while call_count > 0 and has_args == False:
        message = [{"role": "system", "content": f"You are a Linux OS terminal. Your task is to respond exactly as a Linux terminal would. Given this previous output response: {res}, please continue the output accordingly.\
                    If the output contains repetitive information, then you must end the output appropriately. \
                    You must not say anything like 'I'm sorry, but I cannot continue providing the repetitive output. If you need further assistance or specific information, please let me know.'."}]
        new_msg = client.chat.completions.create( 
            model="gpt-3.5-turbo",
            messages = message,
            temperature = 0.1
        )
        next_response = new_msg.choices[0].message.content
        res = res + next_response

        call_count -= 1
        if call_count == 0:
            has_args = False

    final_res = res
    
    add_context(prompt_filepath, cmd, final_res)

    # caching out
    with open(out_filepath, 'w') as outFile:
        outFile.write(final_res)
    outFile.close()

def load_initialPrompts():
    # load the initial prompts here from prompts folder to shelLM folder
    # clear the previous history
    for txtFile in os.listdir('./src/cowrie/shell/prompts'):
        if txtFile.endswith('.txt'):
            #print(txtFile)
            shutil.copy2(f"./src/cowrie/shell/prompts/{txtFile}", './src/cowrie/shell/shelLM')

print("Generating...")
load_initialPrompts()
if len(sys.argv) == 3:
    gen_cmdOutput(sys.argv[2], '')
elif len(sys.argv) == 4:
    gen_cmdOutput(sys.argv[2], sys.argv[3]) 