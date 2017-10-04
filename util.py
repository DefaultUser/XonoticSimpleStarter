#!/usr/bin/env python

# XonoticSimpleStarter
# Copyright (C) <2017>  <Sebastian Schmidt>

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

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup

import os

def is_git_version(path):
    return os.path.isfile(os.path.join(path, "all"))


def error_popup(text):
    content = BoxLayout(orientation='vertical')
    content.add_widget(Label(text=text))
    close_btn = Button(text="OK")
    close_btn.size_hint_y = 0.1
    content.add_widget(close_btn)
    popup = Popup(title="Error", content=content)
    close_btn.bind(on_press=popup.dismiss)
    popup.open()

def win_is_32bit():
    return "PROGRAMFILES(X86)" in os.environ
