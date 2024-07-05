#!/bin/bash

from __future__ import annotations

from openai import OpenAI
import sys

def add_context(prompt_filepath:str, cmd: str, msg: str):
    # write context for single cmd input into prompt file
    with open(prompt_filepath, 'a+') as f:
        f.write("This was the previous Linux command input by the user and your generated output. You must use this as context for the same subsequent commands.\n")
        f.write(f"root@svr04:~# {cmd}")
        f.write(msg)
    f.close()

def gen_cmdOutput(input_cmd: str) -> None:
    # generate any long command outputs here
    call_count = 4

    client = OpenAI(api_key='sk-cowrie-poc-LoDxIQLF8Nki2bpbHYFIT3BlbkFJxxahJfi8yktT0dzYDxCe')
    
    initial_prompt = f"You are a Linux OS terminal. Your task is to respond exactly as a Linux terminal would. The user has input this Linux command {input_cmd}. \
            Use the information provided as a reference and generate the output accordingly."
    prompt = "You must not act like a chatbot. \
            You must not explain any inputs or outputs. \
            You must not in any case have a conversation with user as a chatbot and must not explain your output and do not repeat commands user inputs."
    
    message = [{"role": "system", "content": initial_prompt+prompt}]
    response = client.chat.completions.create( 
        model="gpt-3.5-turbo",
        messages = message,
        temperature = 0.1
    )
    res = response.choices[0].message.content

    out_name = f"{input_cmd}.txt"
    out_filepath = f"./src/cowrie/shell/cache_out/{out_name}"

    while call_count > 0:
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

        call_count -= call_count

    final_res = res
    
    prompt_filepath = f"./src/cowrie/shell/shelLM/{input_cmd}_prompt.txt"
    add_context(prompt_filepath, input_cmd, final_res)

    # caching out
    with open(out_filepath, 'w') as outFile:
        outFile.write(final_res)
    outFile.close()


print("Generating...")
gen_cmdOutput(sys.argv[2]) # get the 1st positional arg after python script name