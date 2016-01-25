import subprocess
import os
from . import util

try:
    from . import Atomic
except ImportError:
    from atomic import Atomic

try:
    from subprocess import DEVNULL  # pylint: disable=no-name-in-module
except ImportError:
    DEVNULL = open(os.devnull, 'wb')


class Run(Atomic):
    def run(self):
        missing_RUN = False
        self.inspect = self._inspect_container()

        if self.inspect:
            self._check_latest()
            # Container exists
            if self.inspect["State"]["Running"]:
                return self._running()
            elif not self.args.display:
                return self._start()

        # Container does not exist
        self.inspect = self._inspect_image()
        if not self.inspect:
            if self.args.display:
                return self.display("Need to pull %s" % self.image)

            self.update()
            self.inspect = self._inspect_image()

        if self.spc:
            if self.command:
                args = self.SPC_ARGS + self.command
            else:
                args = self.SPC_ARGS + self._get_cmd()

            cmd = self.gen_cmd(args)
        else:
            args = self._get_args("RUN")
            if args:
                args += self.command
            else:
                missing_RUN = True
                if self.command:
                    args = self.RUN_ARGS + self.command
                else:
                    args = self.RUN_ARGS + self._get_cmd()

            cmd = self.gen_cmd(args)
            self.display(cmd)
            if self.args.display:
                return

            if missing_RUN:
                subprocess.check_call(cmd, env=self.cmd_env,
                                      shell=True, stderr=DEVNULL,
                                      stdout=DEVNULL)
                return self._start()

        if self.args.quiet:
            self.check_args(cmd)
        if not self.args.display:
            subprocess.check_call(cmd, env=self.cmd_env, shell=True)

    @staticmethod
    def check_args(cmd):
        found_sec_arg = False
        security_args = {
            '--privileged':
                'This container runs without separation and should be '
                'considered the same as root on your system.',
            '--cap-add':
                'Adding capabilities to your container could allow processes '
                'from the container to break out onto your host system.',
            '--security-opt label:disable':
                'Disabling label separation turns off tools like SELinux and '
                'could allow processes from the container to break out onto '
                'your host system.',
            '--net=host':
                'Processes in this container can listen to ports (and '
                'possibly rawip traffic) on the host\'s network.',
            '--pid=host':
                'Processes in this container can see and interact with all '
                'processes on the host and disables SELinux within the '
                'container.',
            '--ipc=host':
                'Processes in this container can see and possibly interact '
                'with all semaphores and shared memory segments on the host '
                'as well as disables SELinux within the container.'
        }

        for sec_arg in security_args:
            if sec_arg in cmd:
                if not found_sec_arg:
                    util.writeOut("\nThis container uses privileged "
                                  "security switches:")
                util.writeOut("\n\033[1mINFO: {}\033[0m "
                              "\n{}{}".format(sec_arg, " " * 6,
                                              security_args[sec_arg]))
                found_sec_arg = True
        if found_sec_arg:
            util.writeOut("\nFor more information on these switches and their "
                          "security implications, consult the manpage for "
                          "'docker run'.\n")
