# **************************************************************************************************
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
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT_TYPE SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************
from colorama import Fore, Style, init
from threading import Event, Condition
from queue import Queue
from time import sleep

from LegoBTLE.Constants.MotorConstant import MotorConstant
from LegoBTLE.Constants.Port import Port
from LegoBTLE.old.Controller.THub import Hub
from LegoBTLE.Device.old.AMotor import SingleMotor

if __name__ == '__main__':
    init()

    Q_cmd_EXEC = Queue(maxsize=200)
    terminate: Event = Event()
    cond: Condition = Condition()
    print(Fore.CYAN + Style.BRIGHT + "{}: Starting up...".format(__name__))
    vorderradantrieb: SingleMotor = SingleMotor(name="Vorderradantrieb", port=Port.A, gearRatio=2.67, cmdQ=Q_cmd_EXEC,
                                                terminate=terminate, debug=True)

    hinterradantrieb: SingleMotor = SingleMotor(name="Hinterradantrieb", port=Port.B, gearRatio=2.67, cmdQ=Q_cmd_EXEC,
                                                terminate=terminate, debug=True)

    lenkung: SingleMotor = SingleMotor(name="Lenkung", port=Port.C, gearRatio=1.00, cmdQ=Q_cmd_EXEC, terminate=terminate,
                                       debug=True)

    print(Style.RESET_ALL)

    hub: Hub = Hub(address='90:84:2B:5E:CF:1F',
                   name="Jeep Hub",
                   cmdQ=Q_cmd_EXEC,
                   terminate=terminate,
                   debug=True)

    hub.startHub()
    hub.E_HUB_STARTED.wait()
    sleep(1.0)
    hub.register(vorderradantrieb)
    hub.register(lenkung)
    hub.register(hinterradantrieb)
    sleep(5.0)
    vorderradantrieb.startMotor()
    sleep(0.5)
    vorderradantrieb.E_MOTOR_STARTED.wait()
    sleep(1)
    hinterradantrieb.startMotor()
    sleep(0.5)
    hinterradantrieb.E_MOTOR_STARTED.wait()
    sleep(1.0)
    lenkung.startMotor()
    sleep(0.5)
    lenkung.E_MOTOR_STARTED.wait()
    sleep(1.0)
    vorderradantrieb.turnForT(milliseconds=2560, direction=MotorConstant.FORWARD, finalAction=MotorConstant.COAST, power=80)
    vorderradantrieb.turnForT(milliseconds=2560, direction=MotorConstant.BACKWARD, finalAction=MotorConstant.BREAK, power=80)
    lenkung.turnForDegrees(degrees=50.2, direction=MotorConstant.LEFT, power=30, finalAction=MotorConstant.COAST)
    hinterradantrieb.turnForT(milliseconds=2560, direction=MotorConstant.BACKWARD, finalAction=MotorConstant.BREAK, power=80)

    while 1:
        sleep(1)
        print("#", end="")
        pass
    #sleep(60.0)
    #terminate.set()
    #hub.E_HUB_TERMINATED.wait(timeout=3.0)
    #vorderradantrieb.E_MOTOR_TERMINATED.wait(timeout=2.0)
    #hinterradantrieb.E_MOTOR_TERMINATED.wait(timeout=2.0)
    #lenkung.E_MOTOR_TERMINATED.wait(timeout=2.0)
    # vorderradantrieb.stopMotor()
    # e1: Event = hub.stopHub()
    # E_motorstop: Event = vorderradantrieb.stopMotor()
    # e1.wait()
    # E_motorstop.wait()

    # hub.startHub()
    # sleep(20)
    # hub.stopHub()
    # vorderradantrieb.switchOffMotor()

    print(Fore.CYAN + Style.BRIGHT + "{}: SHUT DOWN COMPLETE...".format(__name__))