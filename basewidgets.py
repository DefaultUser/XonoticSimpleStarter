#!/usr/bin/env python2

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

import sys
import os

from kivy.core.window import Window
from kivy.properties import StringProperty
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.settings import SettingPath, SettingSpacer
from kivy.uix.treeview import TreeViewNode
from kivy.uix.widget import Widget
from kivy.lang import Builder

if sys.platform in ["win32", "cygwin"]:
    import win32api


Builder.load_file("basewidgets.kv")


class ScrollableLabel(ScrollView):
    text = StringProperty("")


class HSeparator(Widget):
    pass


class VSeparator(Widget):
    pass


class TreeViewContainerNode(BoxLayout, TreeViewNode):
    pass


class WinSettingPath(SettingPath):
    """
    Special SettingPath to compensate for windows drives
    """
    def _create_popup(self, instance):
        # Don't use it unless on windows
        if sys.platform not in ["win32", "cygwin"]:
            return super(WinSettingPath, self)._create_popup(instance)

        # create popup layout
        content = BoxLayout(orientation='vertical', spacing=5)
        popup_width = min(0.95 * Window.width, dp(500))
        self.popup = popup = Popup(
            title=self.title, content=content, size_hint=(None, 0.9),
            width=popup_width)

        # create the filechooser
        self.textinput = textinput = FileChooserListView(
            path=self.value, size_hint=(1, 1), dirselect=True)
        textinput.bind(on_path=self._validate)
        self.textinput = textinput

        # Spinner for drives
        drives = win32api.GetLogicalDriveStrings()
        drives = drives.split("\000")[:-1]
        if self.textinput.path:
            partition = os.path.splitdrive(self.textinput.path)[0] + "\\"
        else:
            partition = "C:\\"
        self.spinner = spinner = Spinner(values=drives, size_hint=(1, None),
                                         height=48, text=partition)
        spinner.bind(text=self.change_drive)

        # construct the content
        content.add_widget(spinner)
        content.add_widget(textinput)
        content.add_widget(SettingSpacer())

        # 2 buttons are created for accept or cancel the current value
        btnlayout = BoxLayout(size_hint_y=None, height='50dp', spacing='5dp')
        btn = Button(text='Ok')
        btn.bind(on_release=self._validate)
        btnlayout.add_widget(btn)
        btn = Button(text='Cancel')
        btn.bind(on_release=self._dismiss)
        btnlayout.add_widget(btn)
        content.add_widget(btnlayout)

        # all done, open the popup !
        popup.open()

    def change_drive(self, *args):
        self.textinput.path = self.spinner.text
