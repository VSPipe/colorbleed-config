import pyblish.api

import os
import hou
from colorbleed.lib import version_up
from colorbleed.action import get_errored_plugins_from_data


class IncrementCurrentFileDeadline(pyblish.api.ContextPlugin):
    """Increment the current file.

    Saves the current scene with an increased version number.

    """

    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    hosts = ["houdini"]
    targets = ["deadline"]

    def process(self, context):

        errored_plugins = get_errored_plugins_from_data(context)
        if any(plugin.__name__ == "HoudiniSubmitPublishDeadline"
                for plugin in errored_plugins):
            raise RuntimeError("Skipping incrementing current file because "
                               "submission to deadline failed.")

        current_filepath = context.data["currentFile"]
        new_filepath = version_up(current_filepath)

        hou.hipFile.save(file_name=new_filepath,
                         save_to_recent_files=True)

