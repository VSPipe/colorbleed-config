import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateRenderSettings(pyblish.api.InstancePlugin):
    """Validates the global render settings

    * File Name Prefix must be as followed:
        * vray: <Scene>/<Layer>/<Layer>
        * arnold: <Scene>/<RenderLayer>/<RenderLayer>
        * default: <Scene>/<RenderLayer>/<RenderLayer>

    * Frame Padding must be:
        * default: 4
    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Render Settings"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    DEFAULT_PADDING = 4
    RENDERER_PREFIX = {"vray": "<Scene>/<Scene>_<Layer>/<Layer>"}
    DEFAULT_PREFIX = "<Scene>/<Scene>_<RenderLayer>/<RenderLayer>"

    def process(self, instance):

        renderer = instance.data['renderer']
        layer_node = instance.data['setMembers']

        # Collect the filename prefix in the renderlayer
        with lib.renderlayer(layer_node):

            render_attrs = lib.RENDER_ATTRS.get(renderer,
                                                lib.RENDER_ATTRS['default'])
            node = render_attrs["node"]
            padding_attr = render_attrs["padding"]
            prefix_attr = render_attrs["prefix"]

            prefix = cmds.getAttr("{}.{}".format(node, prefix_attr))
            padding = cmds.getAttr("{}.{}".format(node, padding_attr))

        fname_prefix = self.RENDERER_PREFIX.get(renderer, self.DEFAULT_PREFIX)
        assert prefix == fname_prefix, (
            "Wrong file name prefix, expecting %s" % fname_prefix
        )
        assert padding == self.DEFAULT_PADDING, (
            "Expecting padding of {} ( {} )".format(self.DEFAULT_PADDING,
                                                    "0"*self.DEFAULT_PADDING)
        )