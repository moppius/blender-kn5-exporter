# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright (C) 2014  Thomas Hagnhofer


import json
import os
import bpy
from inspect import isclass
from mathutils import Matrix, Vector, Quaternion


def convertMatrix(m):
    co, rotation, scale=m.decompose()
    co=convertVector3(co)
    rotation=convertQuaternion(rotation)
    mat_loc = Matrix.Translation(co)
    mat_sca = Matrix.Scale(scale[0],4,(1,0,0)) * Matrix.Scale(scale[2],4,(0,1,0)) * Matrix.Scale(scale[1],4,(0,0,1))
    mat_rot = rotation.to_matrix().to_4x4()
    return mat_loc * mat_rot * mat_sca


def convertVector3(v):
    return Vector((v[0], v[2], -v[1]))


def convertQuaternion(q):
    axis, angle = q.to_axis_angle()
    axis = convertVector3(axis)
    return Quaternion(axis, angle)


def readSettings(file):
    fullPath=os.path.abspath(file)
    dirName=os.path.dirname(fullPath)
    settingsPath=os.path.join(dirName, "settings.json")
    if not os.path.exists(settingsPath):
        return {}
    return json.loads(open(settingsPath, "r").read())


def register_recursive(objects):
    """Registers classes with Blender recursively from modules."""
    for obj in objects:
        if isclass(obj):
            bpy.utils.register_class(obj)
        elif hasattr(obj, "register"):
            obj.register()
        elif hasattr(obj, "REGISTER_CLASSES"):
            register_recursive(obj.REGISTER_CLASSES)
        else:
            print(f"Warning: Failed to find anything to register for '{obj}'")


def unregister_recursive(objects):
    """Unregisters classes from Blender recursively from modules."""
    for obj in reversed(objects):
        if isclass(obj):
            bpy.utils.unregister_class(obj)
        elif hasattr(obj, "unregister"):
            obj.unregister()
        elif hasattr(obj, "REGISTER_CLASSES"):
            unregister_recursive(obj.REGISTER_CLASSES)
        else:
            print(f"Warning: Failed to find anything to unregister for '{obj}'")
