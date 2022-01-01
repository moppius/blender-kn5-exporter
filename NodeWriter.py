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


import mathutils
import math
import os
import re
from . import kn5Helper


NodeClass = {
    "Node" : 1,
    "Mesh" : 2,
    "SkinnedMesh" : 3
}

AcObjects = [r"AC_START_\d+",       r"AC_PIT_\d+",          r"AC_TIME_\d+_L",
             r"AC_TIME_\d+_R",      r"AC_HOTLAP_START_\d+", r"AC_OPEN_FINISH_R",
             r"AC_OPEN_FINISH_L",   r"AC_OPEN_START_L",     r"AC_OPEN_START_R",
             r"AC_AUDIO_.+",        r"AC_CREW_\d+",         r"AC_PIT_\d+"]

class NodeWriter():
    def __init__(self, file, context, settings, warnings, materialsWriter):
        self.nodeSettings=[]
        self.file = file
        self.context = context
        self.settings = settings
        self.warnings = warnings
        self.materialsWriter = materialsWriter
        self.scene = self.context.blend_data.scenes[0]
        self.initAcObjects()
        self.initNodeSettings()

    def initNodeSettings(self):
        self.nodeSettings=[]
        if "nodes" in self.settings:
            for nodeKey in self.settings["nodes"]:
                self.nodeSettings.append(NodeSettings(self.settings, nodeKey))

    def initAcObjects(self):
        self.acObjects=[]
        for o in AcObjects:
            self.acObjects.append(re.compile("^" + o + "$"))

    def isAcObject(self, name):
        for regex in self.acObjects:
            if regex.match(name) is not None:
                return True
        return False

    def write(self):
        self.writeBaseNode(None, "BlenderFile")
        for o in sorted(self.context.blend_data.objects, key=lambda k: len(k.children)):
            if o.parent is None:
                self.writeObject(o)

    def writeObject(self, object):
        if not object.name.startswith("__"):
            if object.type == "MESH":
                if len(object.children) != 0:
                    raise Exception("A mesh cannot contain children ('%s')" % object.name)
                self.writeMeshNode(object)
            else:
                self.writeBaseNode(object, object.name)
            for child in object.children:
                self.writeObject(child)

    def anyChildIsMesh(self, object):
        for child in object.children:
            if child.type=="MESH" or self.anyChildIsMesh(child):
                return True
        return False

    def writeBaseNode(self, object, nodeName):
        nodeData={}
        matrix = None
        childCount = 0
        if object is None:
            matrix = mathutils.Matrix()
            for o in self.context.blend_data.objects:
                if o.parent is None and not o.name.startswith("__"):
                    childCount+=1
        else:
            if not self.isAcObject(object.name) and not self.anyChildIsMesh(object):
                self.warnings.append("Unknown logical object '{0}' might prevent other objects from loading.{1}\tRename it to '__{0}' if you do not want to export it.".format(object.name, os.linesep))
            matrix = kn5Helper.convertMatrix(object.matrix_local)
            for o in object.children:
                if not o.name.startswith("__"):
                    childCount+=1

        nodeData["name"]=nodeName
        nodeData["childCount"]=childCount
        nodeData["active"]=True
        nodeData["transform"]=matrix
        self.writeBaseNodeData(nodeData)


    def writeBaseNodeData(self, nodeData):
        self.writeNodeClass("Node")
        kn5Helper.writeString(self.file, nodeData["name"])
        kn5Helper.writeUInt(self.file, nodeData["childCount"])
        kn5Helper.writeBool(self.file, nodeData["active"])
        kn5Helper.writeMatrix(self.file, nodeData["transform"])


    def writeMeshNode(self, object):
        dividedMeshes=self.splitObjectByMaterials(object)
        dividedMeshes=self.splitMeshesForVertexLimit(dividedMeshes)
        if object.parent is not None or len(dividedMeshes) > 1:
            nodeData={}
            nodeData["name"]=object.name
            nodeData["childCount"]=len(dividedMeshes)
            nodeData["active"]=True
            transformMatrix=mathutils.Matrix()
            if object.parent is not None:
                transformMatrix=kn5Helper.convertMatrix(object.parent.matrix_world.inverted())
            nodeData["transform"]=transformMatrix
            self.writeBaseNodeData(nodeData)
        nodeProperties=NodeProperties(object)
        for nodeSetting in self.nodeSettings:
            nodeSetting.applySettingsToNode(nodeProperties)
        for mesh in dividedMeshes:
            self.writeMesh(object, mesh, nodeProperties)

    def writeNodeClass(self, nodeClass):
        kn5Helper.writeUInt(self.file, NodeClass[nodeClass])

    def writeMesh(self, object, mesh, nodeProperties):
        self.writeNodeClass("Mesh")
        kn5Helper.writeString(self.file, object.name)
        kn5Helper.writeUInt(self.file, 0) #Child count, none allowed
        kn5Helper.writeBool(self.file, True) #Active
        kn5Helper.writeBool(self.file, nodeProperties.castShadows) #castShadows
        kn5Helper.writeBool(self.file, nodeProperties.visible) #isVisible
        kn5Helper.writeBool(self.file, nodeProperties.transparent) #isTransparent
        if len(mesh.vertices)>2**16:
            raise Exception("Only %d vertices per mesh allowed. ('%s')" % (2**16, object.name))
        kn5Helper.writeUInt(self.file, len(mesh.vertices))
        for v in mesh.vertices:
            kn5Helper.writeVector3(self.file, v.co)
            kn5Helper.writeVector3(self.file, v.normal)
            kn5Helper.writeVector2(self.file, v.uv)
            kn5Helper.writeVector3(self.file, v.tangent)
        kn5Helper.writeUInt(self.file, len(mesh.indices))
        for i in mesh.indices:
            kn5Helper.writeUShort(self.file, i)
        if mesh.materialId is None:
            self.warnings.append("No material to mesh '%s' assigned" % object.name)
            kn5Helper.writeUInt(self.file, 0)
        else:
            kn5Helper.writeUInt(self.file, mesh.materialId)
        kn5Helper.writeUInt(self.file, nodeProperties.layer) #Layer
        kn5Helper.writeFloat(self.file, nodeProperties.lodIn) #LOD In
        kn5Helper.writeFloat(self.file, nodeProperties.lodOut) #LOD Out
        self.writeBoundingSphere(mesh.vertices)
        kn5Helper.writeBool(self.file, nodeProperties.renderable) #isRenderable

    def writeBoundingSphere(self, vertices):
        maxX=-999999999
        maxY=-999999999
        maxZ=-999999999
        minX=999999999
        minY=999999999
        minZ=999999999
        for v in vertices:
            co=v.co
            if co[0] > maxX:
               maxX = co[0]
            if co[0] < minX:
               minX = co[0]
            if co[1] > maxY:
               maxY = co[1]
            if co[1] < minY:
               minY = co[1]
            if co[2] > maxZ:
               maxZ = co[2]
            if co[2] < minZ:
               minZ = co[2]

        sphereCenter = [minX + (maxX-minX)/2, minY + (maxY-minY)/2, minZ + (maxZ-minZ)/2]
        sphereRadius = max((maxX-minX)/2,(maxY-minY)/2,(maxZ-minZ)/2)*2
        kn5Helper.writeVector3(self.file, sphereCenter)
        kn5Helper.writeFloat(self.file, sphereRadius)

    def splitObjectByMaterials(self, object):
        meshes=[]
        meshCopy = object.to_mesh(self.scene, True, "RENDER", True, False)
        try:
            uvLayer=meshCopy.tessface_uv_textures.active
            meshVertices=meshCopy.vertices[:]
            meshFaces=meshCopy.tessfaces[:]
            matrix=object.matrix_world
            if len(meshCopy.materials) == 0:
                raise Exception("Object '%s' has no material assigned" % (object.name))
            usedMaterials=set([face.material_index for face in meshFaces])
            for materialIndex in usedMaterials:
                if meshCopy.materials[materialIndex] is None:
                    raise Exception("Material slot %i for object '%s' has no material assigned" % (materialIndex, object.name))
                materialName=meshCopy.materials[materialIndex].name
                if materialName.startswith("__") :
                    raise Exception("Material '%s' is ignored but is used by object '%s'" % (materialName, object.name))
                vertices={}
                indices=[]
                for face in meshCopy.tessfaces:
                    if not materialIndex == face.material_index:
                        continue
                    vertexIndexForFace=0
                    faceIndices=[]
                    for vIndex in face.vertices:
                        v=meshVertices[vIndex]
                        localPosition=matrix * v.co
                        convertedPosition = kn5Helper.convertVector3(localPosition)
                        convertedNormal = kn5Helper.convertVector3(v.normal)
                        uv=(0, 0)
                        if not uvLayer is None:
                            uv=uvLayer.data[face.index].uv[vertexIndexForFace][:2]
                            uv=(uv[0], -uv[1])
                        else:
                            uv=self.calculateUvs(object,meshCopy,materialIndex,localPosition)
                        tangent=(1.0, 0.0, 0.0)
                        vertex=UvVertex(convertedPosition, convertedNormal, uv, tangent)
                        if not vertex in vertices:
                            newIndex=len(vertices)
                            vertices[vertex]=newIndex
                        faceIndices.append(vertices[vertex])
                        vertexIndexForFace+=1
                    indices.extend((faceIndices[1], faceIndices[2], faceIndices[0]))
                    if len(faceIndices) == 4:
                        indices.extend((faceIndices[2], faceIndices[3], faceIndices[0]))
                vertices=[v for v, index in sorted(vertices.items(), key=lambda k: k[1])]
                materialId=self.materialsWriter.materialPositions[materialName]
                meshes.append(Mesh(materialId, vertices, indices))
        finally:
            self.context.blend_data.meshes.remove(meshCopy)
        return meshes

    def splitMeshesForVertexLimit(self, dividedMeshes):
        newMeshes=[]
        limit=2**16
        for mesh in dividedMeshes:
            if len(mesh.vertices)>limit:
                startIndex=0
                while startIndex<len(mesh.indices):
                    vertexIndexMapping={}
                    newIndices=[]
                    for i in range(startIndex, len(mesh.indices), 3):
                        startIndex+=3
                        face=mesh.indices[i:i+3]
                        for faceIndex in face:
                            if not faceIndex in vertexIndexMapping:
                                newIndex=len(vertexIndexMapping)
                                vertexIndexMapping[faceIndex]=newIndex
                            newIndices.append(vertexIndexMapping[faceIndex])
                        if len(vertexIndexMapping) >= limit-3:
                            break
                    vertices=[mesh.vertices[v] for v, index in sorted(vertexIndexMapping.items(), key=lambda k: k[1])]
                    newMeshes.append(Mesh(mesh.materialId, vertices, newIndices))

            else:
                newMeshes.append(mesh)
        return newMeshes

    def calculateUvs(self, object, mesh, materialId, co):
        size=object.dimensions
        x=co[0]/size[0]
        y=co[1]/size[1]
        mat=mesh.materials[materialId]
        textureSlot=kn5Helper.getActiveMaterialTextureSlot(mat)
        if textureSlot is not None:
            x*=textureSlot.scale[0]
            y*=textureSlot.scale[1]
            x+=textureSlot.offset[0]
            y+=textureSlot.offset[1]
        return (x, y)

class NodeProperties:
    def __init__(self, node):
        ac=node.assettoCorsa
        self.name = node.name
        self.lodIn = ac.lodIn
        self.lodOut = ac.lodOut
        self.layer = ac.layer
        self.castShadows = ac.castShadows
        self.visible = ac.visible
        self.transparent = ac.transparent
        self.renderable = ac.renderable

class NodeSettings:
    def __init__(self, settings, nodeSettingsKey):
        self.settings = settings
        self.nodeSettingsKey=nodeSettingsKey
        self.nodeNameMatches=self.convertToMatchesList(nodeSettingsKey)

    def applySettingsToNode(self, node):
        if not self.doesNodeNameMatch(node.name):
            return
        lodIn = self.getNodeLodIn()
        if lodIn is not None:
            node.lodIn = lodIn
        lodOut = self.getNodeLodOut()
        if lodOut is not None:
            node.lodOut = lodOut
        layer = self.getNodeLayer()
        if layer is not None:
            node.layer = layer
        castShadows = self.getNodeCastShadows()
        if castShadows is not None:
            node.castShadows = castShadows
        visible = self.getNodeIsVisible()
        if visible is not None:
            node.visible = visible
        transparent = self.getNodeIsTransparent()
        if transparent is not None:
            node.transparent = transparent
        renderable = self.getNodeIsRenderable()
        if renderable is not None:
            node.renderable = renderable

    def doesNodeNameMatch(self, nodeName):
        for regex in self.nodeNameMatches:
            if regex.match(nodeName) is not None:
                return True
        return False

    def convertToMatchesList(self, key):
        matches=[]
        for subkey in key.split("|"):
            matches.append(re.compile("^" + self.escapeMatchKey(subkey) + "$", re.IGNORECASE))
        return matches

    def escapeMatchKey(self, key):
        wildcardReplacement="__WILDCARD__"
        key=key.replace("*",wildcardReplacement)
        key=re.escape(key)
        key=key.replace(wildcardReplacement, ".*")
        return key

    def getNodeLodIn(self):
        if "lodIn" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["lodIn"]
        return None

    def getNodeLodOut(self):
        if "lodOut" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["lodOut"]
        return None

    def getNodeLayer(self):
        if "layer" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["layer"]
        return None

    def getNodeCastShadows(self):
        if "castShadows" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["castShadows"]
        return None

    def getNodeIsVisible(self):
        if "isVisible" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["isVisible"]
        return None

    def getNodeIsTransparent(self):
        if "isTransparent" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["isTransparent"]
        return None

    def getNodeIsRenderable(self):
        if "isRenderable" in self.settings["nodes"][self.nodeSettingsKey]:
            return self.settings["nodes"][self.nodeSettingsKey]["isRenderable"]
        return None


class UvVertex:
    def __init__(self, co, normal, uv, tangent):
        self.co=co
        self.normal=normal
        self.uv=uv
        self.tangent=tangent
        self.hash=None

    def __hash__(self):
        if self.hash is None:
            self.hash=hash(hash(self.co[0]) ^
                      hash(self.co[1]) ^
                      hash(self.co[2]) ^
                      hash(self.normal[0]) ^
                      hash(self.normal[1]) ^
                      hash(self.normal[2]) ^
                      hash(self.uv[0]) ^
                      hash(self.uv[1]) ^
                      hash(self.tangent[0]) ^
                      hash(self.tangent[1]) ^
                      hash(self.tangent[2]))
        return self.hash

    def __eq__(self, other):
        if self.co[0] != other.co[0] or self.co[1] != other.co[1] or self.co[2] != other.co[2]:
            return False
        if self.normal[0] != other.normal[0] or self.normal[1] != other.normal[1] or self.normal[2] != other.normal[2]:
            return False
        if self.uv[0] != other.uv[0] or self.uv[1] != other.uv[1]:
            return False
        if self.tangent[0] != other.tangent[0] or self.tangent[1] != other.tangent[1] or self.tangent[2] != other.tangent[2]:
            return False
        return True

class Mesh:
    def __init__(self, materialId, vertices, indices):
        self.materialId=materialId
        self.vertices=vertices
        self.indices=indices