import arm.utils
import arm.assets
import bpy
from bpy.types import Menu, Panel, UIList
from bpy.props import *

class ArmBakeListItem(bpy.types.PropertyGroup):
    object_name = bpy.props.StringProperty(
           name="Name",
           description="A name for this item",
           default="")

    res_x = IntProperty(name="X", description="Texture resolution", default=1024)
    res_y = IntProperty(name="Y", description="Texture resolution", default=1024)

class ArmBakeList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We could write some code to decide which icon to use here...
        custom_icon = 'OBJECT_DATAMODE'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            row.prop(item, "object_name", text="", emboss=False, icon=custom_icon)
            col = row.column()
            col.alignment = 'RIGHT'
            col.label(str(item.res_x) + 'x' + str(item.res_y))

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label("", icon=custom_icon)

class ArmBakeListNewItem(bpy.types.Operator):
    # Add a new item to the list
    bl_idname = "arm_bakelist.new_item"
    bl_label = "Add a new item"

    def execute(self, context):
        scn = context.scene
        scn.arm_bakelist.add()
        scn.arm_bakelist_index = len(scn.arm_bakelist) - 1
        return{'FINISHED'}


class ArmBakeListDeleteItem(bpy.types.Operator):
    # Delete the selected item from the list
    bl_idname = "arm_bakelist.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(self, context):
        """ Enable if there's something in the list """
        scn = context.scene
        return len(scn.arm_bakelist) > 0

    def execute(self, context):
        scn = context.scene
        list = scn.arm_bakelist
        index = scn.arm_bakelist_index

        list.remove(index)

        if index > 0:
            index = index - 1

        scn.arm_bakelist_index = index
        return{'FINISHED'}

class ArmBakeButton(bpy.types.Operator):
    '''Bake textures for listed objects'''
    bl_idname = 'arm.bake_textures'
    bl_label = 'Bake'

    def execute(self, context):
        scn = context.scene
        if len(scn.arm_bakelist) == 0:
            return{'FINISHED'}

        # Single user materials
        for o in scn.arm_bakelist:
            ob = scn.objects[o.object_name]
            for slot in ob.material_slots:
                # Temp material already exists
                if slot.material.name.endswith('_temp'):
                    continue
                n = slot.material.name + '_' + ob.name + '_temp'
                if not n in bpy.data.materials:
                    slot.material = slot.material.copy()
                    slot.material.name = n

        # Images for baking
        for o in scn.arm_bakelist:
            ob = scn.objects[o.object_name]
            for slot in ob.material_slots:
                mat = slot.material
                img_name = mat.name[:-5] + '_baked'
                sc = scn.arm_bakelist_scale / 100
                rx = o.res_x * sc
                ry = o.res_y * sc
                # Get image
                if img_name not in bpy.data.images:# or bpy.data.images[img_name].size[0] != rx or bpy.data.images[img_name].size[1] != ry:
                    img = bpy.data.images.new(img_name, rx, ry)
                else:
                    img = bpy.data.images[img_name]
                # Add image nodes
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                if 'Baked Image' in nodes:
                    img_node = nodes['Baked Image']
                else:
                    img_node = nodes.new('ShaderNodeTexImage')
                    img_node.name = 'Baked Image'
                    img_node.location = (100, 100)
                    img_node.image = img
                img_node.select = True
                nodes.active = img_node
        
        # Unwrap
        active = bpy.context.scene.objects.active
        for o in scn.arm_bakelist:
            ob = scn.objects[o.object_name]
            if len(ob.data.uv_textures) == 0:
                bpy.context.scene.objects.active = ob
                bpy.ops.uv.lightmap_pack("EXEC_SCREEN", PREF_CONTEXT="ALL_FACES")
                ob.data.uv_textures[0].name += "_baked"
        bpy.context.scene.objects.active = active

        # Materials for runtime
        for o in scn.arm_bakelist:
            ob = scn.objects[o.object_name]
            for slot in ob.material_slots:
                n = slot.material.name[:-5] + '_baked'
                if not n in bpy.data.materials:
                    mat = bpy.data.materials.new(name=n)
                    mat.use_nodes = True
                    mat.use_fake_user = True
                    nodes = mat.node_tree.nodes
                    img_node = nodes.new('ShaderNodeTexImage')
                    img_node.name = 'Baked Image'
                    img_node.location = (100, 100)
                    img_node.image = bpy.data.images[n]
                    mat.node_tree.links.new(img_node.outputs[0], nodes['Diffuse BSDF'].inputs[0])

        # Bake
        bpy.ops.object.select_all(action='DESELECT')
        for o in scn.arm_bakelist:
            scn.objects[o.object_name].select = True
        scn.objects.active = scn.objects[scn.arm_bakelist[0].object_name]
        bpy.ops.object.bake('INVOKE_DEFAULT', type='COMBINED')
        bpy.ops.object.select_all(action='DESELECT')

        return{'FINISHED'}

class ArmBakeApplyButton(bpy.types.Operator):
    '''Pack baked textures and restore materials'''
    bl_idname = 'arm.bake_apply'
    bl_label = 'Apply'

    def execute(self, context):
        scn = context.scene
        if len(scn.arm_bakelist) == 0:
            return{'FINISHED'}
        arm.assets.invalidate_unpacked_data(None, None)
        for o in scn.arm_bakelist:
            ob = scn.objects[o.object_name]
            for slot in ob.material_slots:
                mat = slot.material
                # Temp material exists
                if mat.name.endswith('_temp'):
                    # Save images
                    img_name = mat.name[:-5] + '_baked'
                    bpy.data.images[img_name].pack(as_png=True)
                    bpy.data.images[img_name].save()
                    # Remove temp materials
                    old = slot.material
                    slot.material = bpy.data.materials[old.name.split('_' + ob.name)[0]]
                    bpy.data.materials.remove(old, True)

        return{'FINISHED'}

class ArmBakeSpecialsMenu(bpy.types.Menu):
    bl_label = "Bake"
    bl_idname = "arm_bakelist_specials"

    def draw(self, context):
        layout = self.layout
        layout.operator("arm.bake_add_all")

class ArmBakeAddAllButton(bpy.types.Operator):
    '''Fill the list with scene objects'''
    bl_idname = 'arm.bake_add_all'
    bl_label = 'Add All'

    def execute(self, context):
        scn = context.scene
        scn.arm_bakelist.clear()
        for ob in scn.objects:
            if ob.type == 'MESH':
                scn.arm_bakelist.add().object_name = ob.name
        return{'FINISHED'}

def register():
    bpy.utils.register_class(ArmBakeListItem)
    bpy.utils.register_class(ArmBakeList)
    bpy.utils.register_class(ArmBakeListNewItem)
    bpy.utils.register_class(ArmBakeListDeleteItem)
    bpy.utils.register_class(ArmBakeButton)
    bpy.utils.register_class(ArmBakeApplyButton)
    bpy.utils.register_class(ArmBakeSpecialsMenu)
    bpy.utils.register_class(ArmBakeAddAllButton)
    bpy.types.Scene.arm_bakelist_scale = FloatProperty(name="Resolution", description="Resolution scale", default=100.0, min=1, max=1000, soft_min=1, soft_max=100.0, subtype='PERCENTAGE')
    bpy.types.Scene.arm_bakelist = bpy.props.CollectionProperty(type=ArmBakeListItem)
    bpy.types.Scene.arm_bakelist_index = bpy.props.IntProperty(name="Index for my_list", default=0)

def unregister():
    bpy.utils.unregister_class(ArmBakeListItem)
    bpy.utils.unregister_class(ArmBakeList)
    bpy.utils.unregister_class(ArmBakeListNewItem)
    bpy.utils.unregister_class(ArmBakeListDeleteItem)
    bpy.utils.unregister_class(ArmBakeButton)
    bpy.utils.unregister_class(ArmBakeApplyButton)
    bpy.utils.unregister_class(ArmBakeSpecialsMenu)
    bpy.utils.unregister_class(ArmBakeAddAllButton)