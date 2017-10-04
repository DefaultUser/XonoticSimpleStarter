#!/usr/bin/env python

# XonoticSimpleStarter
# Copyright (C) <2016>  <Sebastian Schmidt>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from kivy.app import App
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.support import install_twisted_reactor
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.treeview import TreeViewLabel
from kivy.core.text import LabelBase
from kivy.properties import DictProperty, BooleanProperty
from kivy.event import EventDispatcher
from kivy.logger import Logger

install_twisted_reactor()

from twisted.internet.protocol import ProcessProtocol, Factory
from twisted.internet import defer, error, reactor, endpoints
from twisted.web.client import HTTPDownloader
from twisted.python.procutils import which
import os
import platform
import sys
import re
import tempfile
import shutil

import util


excludes_posix = ["--exclude=/*.exe", "--exclude=/gmqcc/*.exe",
                  "--exclude=/bin32", "--exclude=/*.dll",
                  "--exclude=/bin64"]
excludes_darwin = ["--exclude=/xonotic-linux*",
                   "--exclude=/gmqcc/gmqcc.linux*"]
excludes_linux64 = ["--exclude=/Xonotic*.app",
                    "--exclude=/xonotic-osx-*",
                    "--exclude=/gmqcc/gmqcc.osx"]
excludes_linux64_no32 = ["--exclude=/xonotic-linux32-*",
                         "--exclude=/gmqcc/gmqcc.linux32"]
excludes_linux32 = ["--exclude=/Xonotic*.app",
                    "--exclude=/xonotic-osx-*",
                    "--exclude=/gmqcc/gmqcc.osx",
                    "--exclude=/xonotic-linux64-*",
                    "--exclude=/gmqcc/gmqcc.linux64"]
excludes_windows = ["--exclude=/xonotic-linux*",
                    "--exclude=/xonotic-osx-*",
                    "--exclude=/Xonotic*.app",
                    "--exclude=/gmqcc/gmqcc.linux*",
                    "--exclude=/gmqcc/gmqcc.osx"]
excludes_windows32 = ["--exclude=/xonotic.exe",
                      "--exclude=/xonotic-wgl.exe",
                      "--exclude=/xonotic-dedicated.exe",
                      "--exclude=/gmqcc/gmqcc-x64.exe",
                      "--exclude=/bin64"]
excludes_windows64 = ["--exclude=/xonotic-x86.exe",
                      "--exclude=/xonotic-x86-wgl.exe",
                      "--exclude=/xonotic-x86-dedicated.exe",
                      "--exclude=/gmqcc/gmqcc.exe",
                      "--exclude=/bin32",
                      "--exclude=/*.dll"]

rsync_options = ["-Prtzil", "-y", "--executability", "--delete-after",
                 "--delete-excluded", "--stats"]

Builder.load_file("updater.kv")


class chmodProtocol(ProcessProtocol, EventDispatcher):
    def connectionMade(self):
        self.finished = defer.Deferred()

    def processEnded(self, reason):
        if reason.check(error.ProcessDone):
            self.finished.callback(True)
        else:
            self.finished.errback(reason)


class UpdateProtocol(ProcessProtocol, EventDispatcher):
    status = DictProperty({"running": False, "error": None, "current": None,
                           "currentProgress": 0, "filesConsidered": 0,
                           "filesDone": 0, "currentSpeed": "0kB/s"})
    progress_pattern = re.compile(r"\s*([\d,]+)\s+(\d{1,3}%)\s+"
                                  r"(\d+(\.\d+)?(G|M|K)?B\/s)\s+"
                                  r"(\d+\:\d{2}\:\d{2})", re.IGNORECASE)

    def connectionMade(self):
        self.updateFinished = defer.Deferred()

    def outReceived(self, data):
        Logger.info(data.replace("\r", "\n"))
        for elem in data.splitlines():
            if elem.lower().startswith("receiving file list"):
                self.status["running"] = True
            elif elem.lower().endswith("files to consider"):
                self.status["filesConsidered"] = int(elem.split()[0])
            elif elem.startswith(">f"):
                self.status["current"] = elem.split()[-1]
                self.status["currentProgress"] = 0
                self.status["currentSpeed"] = "0kB/s"

            match = UpdateProtocol.progress_pattern.search(elem)
            if match:
                size, progress, speed, _, _, time = match.groups()
                self.status["currentProgress"] = int(progress[:-1])
                self.status["currentSpeed"] = speed
                if self.status["currentProgress"] == 100:
                    self.status["filesDone"] += 1

    def errReceived(self, data):
        Logger.info(data.replace("\r", "\n"))
        self.status["error"] = data
        self.status["running"] = False
        self.status["current"] = None
        self.status["currentProgress"] = 0
        self.status["currentSpeed"] = "0kB/s"

    def processEnded(self, reason):
        self.status["running"] = False
        if reason.check(error.ProcessDone):
            self.updateFinished.callback(True)
        else:
            self.updateFinished.errback(reason)


class UpdatePane(BoxLayout):
    updateRunning = BooleanProperty(False)

    def get_updater_path(self, xon_path):
        relpath = ["misc", "tools", "rsync-updater"]
        return os.path.join(xon_path, *relpath)

    @defer.inlineCallbacks
    def prepare_update(self, xon_path):
        self.ids["output"].text = "Preparing for update...\n"

        # download rsync if needed
        if platform.system() == "Windows":
            # windows needs to download dependencies
            files = ["chmod.exe", "rsync.exe", "cygwin1.dll", "cygintl-8.dll",
                     "cygiconv-2.dll", "cyggcc_s-1.dll"]
        elif platform.system() == "Linux" or platform.system() == "Darwin":
            # macOS and Linux need to have rsync installed
            if not which("rsync"):
                raise EnvironmentError("Could not find rsync, is it installed?")
            defer.returnValue(None)
        else:
            raise EnvironmentError("Unsupported Platform")

        # Windows only code
        self.tempdir = tempfile.mkdtemp(dir=tempfile.gettempdir(),
                                        prefix="xonotic-updater")
        myEndpoint = endpoints.clientFromString(reactor, "tls:gitlab.com:443")
        download_url = "https://gitlab.com/xonotic/xonotic/raw/master/misc/"\
            "tools/rsync-updater/"

        updater_path = self.get_updater_path(xon_path)
        # create part of the folder structure
        if sys.version_info.major > 2:
            os.makedirs(updater_path, exist_ok=True)
        else:
            try:
                os.makedirs(updater_path)
            except OSError as e:
                if e.errno != os.errno.EEXIST:
                    Logger.error(e)
                    raise

        for f in files:
            fullpath = os.path.join(updater_path, f)
            # download files if needed
            if not os.path.isfile(fullpath):
                factory = HTTPDownloader(download_url + f, fullpath)
                client = yield myEndpoint.connect(factory)
                yield factory.deferred
                self.ids["output"].text += "Downloaded " + f + "\n"
            # copy to temp folder, file descriptors are blocked otherwise
            shutil.copy(fullpath, self.tempdir)

    def do_cleanup(self):
        if hasattr(self, "process"):
            del self.process
        if platform.system() == "Windows" and hasattr(self, "tempdir"):
            def rm_tempdir():
                shutil.rmtree(self.tempdir)
                self.updateRunning = False

            def on_chmod_error(error):
                util.error_popup(str(error))
                rm_tempdir()
            # permissions
            config = App.get_running_app().config
            xon_path = config.get('Xonotic', 'xon_path')
            chmod_proto = chmodProtocol()
            chmod = os.path.join(self.tempdir, "chmod.exe")
            reactor.spawnProcess(chmod_proto, chmod,
                                 args=[chmod, "-R", "a+x", xon_path],
                                 env=os.environ, path=xon_path,
                                 usePTY=False)
            # remove temp file
            chmod_proto.addCallback(rm_tempdir)
            chmod_proto.addErrback(on_chmod_error)
        else:
            self.updateRunning = False

    def on_update_success(self, success):
        self.ids["output"].text += "\n[color=009300]Update Successful[/color]\n"
        self.ids["progress_files"].value = self.ids["progress_files"].max
        self.do_cleanup()

    def on_update_fail(self, error):
        self.do_cleanup()

    def update_error(self, error):
        self.ids["output"].text += "[color=FF0000]An error occured:[/color]\n"
        self.ids["output"].text += str(error) + "\n"

    def update_status(self, instance, status):
        self.ids["output"].text = ("Running: {running}\n"
                                   "{filesConsidered} files to consider\n"
                                   "{filesDone} files updated\n"
                                   "Current File: {current}\n"
                                   "Current Speed: {currentSpeed}\n\n").format(
                                       **status)
        self.ids["progress_current"].value = status["currentProgress"]
        self.ids["progress_files"].max = status["filesConsidered"]
        self.ids["progress_files"].value = status["filesDone"]
        if status["error"] is not None:
            self.update_error(status["error"])

    @defer.inlineCallbacks
    def do_update(self):
        config = App.get_running_app().config
        xon_path = config.get('Xonotic', 'xon_path')
        if hasattr(self, "process"):
            util.error_popup("Update already running")
            defer.returnValue(None)
        if util.is_git_version(xon_path):
            util.error_popup("This seems to be a git repo\n"
                             "Please use the all script")
            defer.returnValue(None)
        try:
            self.updateRunning = True
            yield self.prepare_update(xon_path)
            self.ids["output"].text = "Starting update...\n"
        except EnvironmentError as e:
            util.error_popup(str(e))
            self.ids["output"].text = ""
            self.do_cleanup()
            defer.returnValue(None)
        self.update_proto = UpdateProtocol()
        self.update_proto.bind(status=self.update_status)

        if config.getboolean('Update', 'autobuild'):
            buildtype = "autobuild"
        else:
            buildtype = "release"
        INCLUDE_ALL = config.getboolean('Update', 'INCLUDE_ALL')
        INCLUDE_32BIT = config.getboolean('Update', 'INCLUDE_32BIT')
        quality = "-" + config.get('Update', 'quality')
        if quality == "-normal":
            quality = ""
        url = "rsync://beta.xonotic.org/{buildtype}-Xonotic{quality}/".format(
            buildtype=buildtype, quality=quality)

        if platform.system() == "Windows":
            rsync = os.path.join(self.tempdir, "rsync.exe")
            args = [rsync, ] + rsync_options
            if not INCLUDE_ALL:
                args += excludes_windows
                if util.win_is_32bit():
                    args += excludes_linux32
                elif not INCLUDE_32BIT:
                    args += excludes_windows64
        elif platform.system() == "Darwin":
            rsync = "rsync"
            args = [rsync, ] + rsync_options
            if not INCLUDE_ALL:
                args += excludes_posix + excludes_darwin
        else:
            # Linux
            rsync = "rsync"
            args = [rsync, ] + rsync_options
            if not INCLUDE_ALL:
                args += excludes_posix
                if platform.machine() == "i386":
                    args += excludes_linux32
                else:
                    args += excludes_linux64
                    if not INCLUDE_32BIT:
                        args += excludes_linux64_no32
        args += [url, xon_path]
        self.process = reactor.spawnProcess(self.update_proto, rsync,
                                            args=args, env=os.environ,
                                            path=xon_path, usePTY=False)
        self.update_proto.updateFinished.addCallback(self.on_update_success)
        self.update_proto.updateFinished.addErrback(self.on_update_fail)

    def cancel(self):
        if hasattr(self, "process"):
            if self.process.pid:
                self.process.signalProcess("TERM")

