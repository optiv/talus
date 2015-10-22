#!/usr/bin/env python
# encoding: utf-8

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from talus.tools.tool_template import ToolTemplate
from talus.components.component_template import ComponentTemplate

component = ComponentTemplate(prefix="yoyo")
tool = ToolTemplate()
tool.run(arg1="Apples", arg2="Oranges", comp1=component, iters=3)
