# Copyright (c) 2009-2014 Upi Tamminen <desaster@gmail.com>
# See the COPYRIGHT file for more information

"""
This module contains code to run a command
"""

from __future__ import annotations

import os
import re
import shlex
import stat
import time
from openai import OpenAI
from collections.abc import Callable

from twisted.internet import error
from twisted.python import failure, log

from cowrie.core.config import CowrieConfig
from cowrie.shell import fs


class HoneyPotCommand:
    """
    This is the super class for all commands in cowrie/commands
    """

    safeoutfile: str = ""

    def __init__(self, protocol, *args):
        # keeping track of command count
        #self.cmd_count = {} # keeps resetting here

        self.protocol = protocol
        self.args = list(args)
        self.environ = self.protocol.cmdstack[0].environ
        self.fs = self.protocol.fs
        self.data: bytes = b""  # output data
        self.input_data: None | (
            bytes
        ) = None  # used to store STDIN data passed via PIPE
        self.writefn: Callable[[bytes], None] = self.protocol.pp.outReceived
        self.errorWritefn: Callable[[bytes], None] = self.protocol.pp.errReceived
        # MS-DOS style redirect handling, inside the command
        # TODO: handle >>, 2>, etc
        if ">" in self.args or ">>" in self.args:
            if self.args[-1] in [">", ">>"]:
                self.errorWrite("-bash: parse error near '\\n' \n")
                return
            self.writtenBytes = 0
            self.writefn = self.write_to_file
            if ">>" in self.args:
                index = self.args.index(">>")
                b_append = True
            else:
                index = self.args.index(">")
                b_append = False
            self.outfile = self.fs.resolve_path(
                str(self.args[(index + 1)]), self.protocol.cwd
            )
            del self.args[index:]
            p = self.fs.getfile(self.outfile)
            if (
                not p
                or not p[fs.A_REALFILE]
                or p[fs.A_REALFILE].startswith("honeyfs")
                or not b_append
            ):
                tmp_fname = "{}-{}-{}-redir_{}".format(
                    time.strftime("%Y%m%d-%H%M%S"),
                    self.protocol.getProtoTransport().transportId,
                    self.protocol.terminal.transport.session.id,
                    re.sub("[^A-Za-z0-9]", "_", self.outfile),
                )
                self.safeoutfile = os.path.join(
                    CowrieConfig.get("honeypot", "download_path"), tmp_fname
                )
                perm = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
                try:
                    self.fs.mkfile(self.outfile, 0, 0, 0, stat.S_IFREG | perm)
                except fs.FileNotFound:
                    # The outfile locates at a non-existing directory.
                    self.errorWrite(
                        f"-bash: {self.outfile}: No such file or directory\n"
                    )
                    self.writefn = self.write_to_failed
                    self.outfile = None
                    self.safeoutfile = ""
                except fs.PermissionDenied:
                    # The outfile locates in a file-system that doesn't allow file creation
                    self.errorWrite(f"-bash: {self.outfile}: Permission denied\n")
                    self.writefn = self.write_to_failed
                    self.outfile = None
                    self.safeoutfile = ""

                else:
                    with open(self.safeoutfile, "ab"):
                        self.fs.update_realfile(
                            self.fs.getfile(self.outfile), self.safeoutfile
                        )
            else:
                self.safeoutfile = p[fs.A_REALFILE]

    def write(self, data: str) -> None:
        """
        Write a string to the user on stdout
        """
        self.writefn(data.encode("utf8"))

    def writeBytes(self, data: bytes) -> None:
        """
        Like write() but input is bytes
        """
        self.writefn(data)

    def errorWrite(self, data: str) -> None:
        """
        Write errors to the user on stderr
        """
        self.errorWritefn(data.encode("utf8"))

    def check_arguments(self, application, args):
        files = []
        for arg in args:
            path = self.fs.resolve_path(arg, self.protocol.cwd)
            if self.fs.isdir(path):
                self.errorWrite(
                    f"{application}: error reading `{arg}': Is a directory\n"
                )
                continue
            files.append(path)
        return files

    def set_input_data(self, data: bytes) -> None:
        self.input_data = data

    def write_to_file(self, data: bytes) -> None:
        with open(self.safeoutfile, "ab") as f:
            f.write(data)
        self.writtenBytes += len(data)
        self.fs.update_size(self.outfile, self.writtenBytes)

    def write_to_file_str(self, msg: str, filename: str) -> None:
        full_filepath = f"./src/cowrie/shell/cache_out/{filename}.txt"
        with open(full_filepath, 'w') as outFile:
            outFile.write(msg)
        outFile.close()
    
    def add_context(self, prompt_file: str, input_cmd: str, msg: str) -> None:
        # write context for single cmd input into prompt file
        prompt_filepath = f"./src/cowrie/shell/shelLM/{prompt_file}"
        with open(prompt_filepath, 'a+') as f:
            f.write("This was the previous Linux command input by the user and your generated output. You must use this as context for the same subsequent commands.\n")
            f.write(f"root@svr04:~# {input_cmd}\n")
            f.write(msg)
        f.close()

    def write_to_failed(self, data: bytes) -> None:
        pass

    def start(self) -> None: # only starts eachtime we input command, not called during startup
        if self.writefn != self.write_to_failed:
            self.call()
        self.exit()

    def call(self) -> None:
        self.write(f"Hello World! [{self.args!r}]\n")

    def exit(self) -> None:
        """
        Sometimes client is disconnected and command exits after. So cmdstack is gone
        """
        if (
            self.protocol
            and self.protocol.terminal
            and hasattr(self, "safeoutfile")
            and self.safeoutfile
        ):
            if hasattr(self, "outfile") and self.outfile:
                self.protocol.terminal.redirFiles.add((self.safeoutfile, self.outfile))
            else:
                self.protocol.terminal.redirFiles.add((self.safeoutfile, ""))

        if len(self.protocol.cmdstack):
            self.protocol.cmdstack.pop()
            if len(self.protocol.cmdstack):
                self.protocol.cmdstack[-1].resume()
        else:
            ret = failure.Failure(error.ProcessDone(status=""))
            # The session could be disconnected already, when his happens .transport is gone
            try:
                self.protocol.terminal.transport.processEnded(ret)
            except AttributeError:
                pass

    def handle_CTRL_C(self) -> None:
        log.msg("Received CTRL-C, exiting..")
        self.write("^C\n")
        self.exit()

    def lineReceived(self, line: str) -> None:
        log.msg(f"QUEUED INPUT: {line}")
        # FIXME: naive command parsing, see lineReceived below
        # line = "".join(line)
        self.protocol.cmdstack[0].cmdpending.append(shlex.split(line, posix=True))

    def resume(self) -> None:
        pass

    def handle_TAB(self) -> None:
        pass

    def handle_CTRL_D(self) -> None:
        pass

    def runLLM(self, cmd_input: str, prompt_file: str, cmd_count) -> None:
        # self.write(f"This is the user input {cmd_input}\n")
        # self.write(f"This is cmd dictionary: {cmd_count}\n")
        
        if cmd_count[cmd_input] == 1:
            client = OpenAI(api_key= 'your key here')

            initial_prompt = f"You are a Linux OS terminal. Your task is to respond exactly as a Linux terminal would. The user has input this Linux command {cmd_input}. \
                Use the information provided as a reference and generate the output accordingly."
            
            prompt = "You must not act like a chatbot. \
                You must not explain any inputs or outputs. \
                You must not in any case have a conversation with user as a chatbot and must not explain your output and do not repeat commands user inputs."

            with open(f"./src/cowrie/shell/shelLM/{prompt_file}", 'r') as pFile:
                    personality_prompt = pFile.read()

            message = [{"role": "system", "content": initial_prompt+personality_prompt+prompt}]
            res = client.chat.completions.create( 
                model="gpt-3.5-turbo",
                messages = message,
                temperature = 0.1 # randomness of output
            )
            msg = res.choices[0].message.content

            # caching
            name = f"{cmd_input}"
            self.write_to_file_str(msg, name)
            # update with context for LLM
            self.add_context(prompt_file, cmd_input, msg)
        
        else:
            log.msg(cmd_count)
            filepath = f"./src/cowrie/shell/cache_out/{cmd_input}.txt"
            log.msg(f"Reading from: {filepath}")
            with open(filepath, encoding='utf-8') as readFile:
                self.write(readFile.read())
                self.write("\n")

    def __repr__(self) -> str:
        return str(self.__class__.__name__)
