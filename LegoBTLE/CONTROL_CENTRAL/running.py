﻿# **************************************************************************************************
#  MIT License                                                                                     *
#                                                                                                  *
#  Copyright (c) 2021 Dietrich Christopeit                                                         *
#                                                                                                  *
#  Permission is hereby granted, free of charge, to any person obtaining a copy                    *
#  of this software and associated documentation files (the "Software"), to deal                   *
#  in the Software without restriction, including without limitation the rights                    *
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell                       *
#  copies of the Software, and to permit persons to whom the Software is                           *
#  furnished to do so, subject to the following conditions:                                        *
#                                                                                                  *
#  The above copyright notice and this permission notice shall be included in all                  *
#  copies or substantial portions of the Software.                                                 *
#                                                                                                  *
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR                      *
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,                        *
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************
import asyncio
from asyncio import Event
from asyncio.futures import Future
from random import uniform
from typing import Union, Any, Optional


class CMD_Sequence:
    
    def __init__(self, cmd_sequence: Optional[Future]):

        self.cmd_executor = None
        self._cmd_sequence = cmd_sequence
        self._proceed: Event = Event()
        return
    
    @property
    def cmd_sequence(self) -> [Future]:
        return self._cmd_sequence
    
    @cmd_sequence.setter
    def cmd_sequence(self, seq: Union[Future, Any]):
        self._cmd_sequence = (asyncio.ensure_future(self.cmd_executor(v)) for v in seq.values())
        return
    
    def install_cmd_executor(self, cmd_executor):
        self.cmd_executor = cmd_executor
        return
    
    async def run_until_complete(self, cmd_sequence: [Future] = None) -> {}:
        if cmd_sequence is not None:
            self._cmd_sequence = cmd_sequence
        run_sequence_values = (asyncio.ensure_future(v) for v in self._cmd_sequence.values())
        run_sequence_keys = list(self._cmd_sequence.keys())
        r = await asyncio.gather(*run_sequence_values)
        results = {k: r[run_sequence_keys.index(k)] for k in run_sequence_keys}
        return results

    async def exec(self, cmd: [], result=None, *result_args, wait: bool = False) -> Future:
        r = Future()
        await self._proceed.wait()
        if wait:
            self._proceed.clear()
            self.cmd_executor()
    
        else:
            dt = uniform(3.0, 3.0)
            print(f"{cmd}:WAITING {dt}...")
            await asyncio.sleep(dt)
        if result is None:
            r.set_result(True)
        else:
            if result_args is None:
                raise ReferenceError(f"The parameter args is None whereas result-cmd is {result}...")
            r.set_result(result(*result_args))
        return r