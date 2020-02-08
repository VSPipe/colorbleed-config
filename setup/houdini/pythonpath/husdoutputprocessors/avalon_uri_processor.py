import hou
import husdoutputprocessors.base as base
import os
import re
import logging

import colorbleed.houdini.usd as usdlib


def _get_project_publish_template():
    """Return publish template from database for current project"""
    from avalon import io
    project = io.find_one({"type": "project"},
                          projection={"config.template.publish": True})
    return project["config"]["template"]["publish"]


class AvalonURIOutputProcessor(base.OutputProcessorBase):
    """Process Avalon URIs into their full path equivalents.

    """

    _parameters = None
    _param_prefix = 'avalonurioutputprocessor_'
    _parms = {
        "use_publish_paths": _param_prefix + "use_publish_paths"
    }

    def __init__(self):
        """ There is only one object of each output processor class that is
            ever created in a Houdini session. Therefore be very careful
            about what data gets put in this object.
        """
        self._template = None
        self._use_publish_paths = False
        self._cache = dict()

    def displayName(self):
        return 'Avalon URI Output Processor'

    def parameters(self):

        if not self._parameters:
            parameters = hou.ParmTemplateGroup()
            use_publish_path = hou.ToggleParmTemplate(
                name=self._parms["use_publish_paths"],
                label='Resolve Reference paths to publish paths',
                default_value=False,
                help=("When enabled any paths for Layers, References or "
                      "Payloads are resolved to published master versions.\n"
                      "This is usually only used by the publishing pipeline, "
                      "but can be used for testing too."))
            parameters.append(use_publish_path)
            self._parameters = parameters.asDialogScript()

        return self._parameters

    def beginSave(self, config_node, t):
        self._template = _get_project_publish_template()

        parm = self._parms["use_publish_paths"]
        self._use_publish_paths = config_node.parm(parm).evalAtTime(t)
        self._cache.clear()

    def endSave(self):
        self._template = None
        self._use_publish_paths = None
        self._cache.clear()

    def processAsset(self,
                     asset_path,
                     asset_path_for_save,
                     referencing_layer_path,
                     asset_is_layer,
                     for_save):
        """
        Args:
            asset_path (str): The incoming file path you want to alter or not.
            asset_path_for_save (bool): Whether the current path is a
                referenced path in the USD file. When True, return the path
                you want inside USD file.
            referencing_layer_path (str): ???
            asset_is_layer (bool): Whether this asset is a USD layer file.
                If this is False, the asset is something else (for example,
                a texture or volume file).
            for_save (bool): Whether the asset path is for a file to be saved
                out. If so, then return actual written filepath.

        Returns:
            The refactored asset path.

        """

        # Retrieve from cache if this query occurred before (optimization)
        cache_key = (asset_path, asset_path_for_save, asset_is_layer, for_save)
        if cache_key in self._cache:
            return self._cache[cache_key]

        relative_template = "{asset}_{subset}.{ext}"
        uri_data = usdlib.parse_avalon_uri(asset_path)
        if uri_data:

            if for_save:
                # Set save output path to a relative path so other
                # processors can potentially manage it easily?
                path = relative_template.format(**uri_data)

                print("Avalon URI Resolver: %s -> %s" % (asset_path, path))
                self._cache[cache_key] = path
                return path

            if self._use_publish_paths:
                # Resolve to an Avalon published asset for embedded paths
                path = self._get_usd_master_path(**uri_data)
            else:
                path = relative_template.format(**uri_data)

            print("Avalon URI Resolver: %s -> %s" % (asset_path, path))
            self._cache[cache_key] = path
            return path

        self._cache[cache_key] = asset_path
        return asset_path

    def _get_usd_master_path(self,
                             asset,
                             subset,
                             ext):
        """Get the filepath for a .usd file of a subset.

        This will return the path to an unversioned master file generated by
        `usd_master_file.py`.

        """

        from avalon import api, io

        PROJECT = api.Session["AVALON_PROJECT"]
        asset_doc = io.find_one({"name": asset,
                                 "type": "asset"})
        if not asset_doc:
            raise RuntimeError("Invalid asset name: '%s'" % asset)

        root = api.registered_root()
        path = self._template.format(**{
            "root": root,
            "project": PROJECT,
            "silo": asset_doc["silo"],
            "asset": asset_doc["name"],
            "subset": subset,
            "representation": ext,
            "version": 0  # stub version zero
        })

        # Remove the version folder
        subset_folder = os.path.dirname(os.path.dirname(path))
        master_folder = os.path.join(subset_folder, "master")
        fname = "{0}.{1}".format(subset, ext)

        return os.path.join(master_folder, fname).replace("\\", "/")


output_processor = AvalonURIOutputProcessor()


def usdOutputProcessor():
    return output_processor

