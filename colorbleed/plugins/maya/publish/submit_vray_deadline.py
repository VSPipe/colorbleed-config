import getpass
import json
import os
from copy import deepcopy

import pyblish.api

from avalon import api
from avalon.vendor import requests

from maya import cmds


class VraySubmitDeadline(pyblish.api.InstancePlugin):
    """Export the scene to `.vrscene` files per frame per render layer

    vrscene files will be written out based on the following template:
        <project>/vrayscene/<Scene>/<Scene>_<Layer>/<Layer>

    A dependency job will be added for each layer to render the frames
    through VRay Standalone

    """
    label = "Submit to Deadline ( vrscene )"
    order = pyblish.api.IntegratorOrder
    hosts = ["maya"]
    families = ["colorbleed.vrayscene"]
    targets = ["local"]

    def process(self, instance):

        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        context = instance.context

        deadline_url = "{}/api/jobs".format(AVALON_DEADLINE)
        deadline_user = context.data.get("deadlineUser", getpass.getuser())

        code = context.data["code"]
        filepath = context.data["currentFile"]
        filename = os.path.basename(filepath)
        task_name = "{} - {}".format(filename, instance.name)

        batch_name = "{} - (vrscene)".format(filename)
        if code:
            batch_name = "{0} - {1}".format(code, batch_name)

        # Get the output template for vrscenes
        vrscene_output = instance.data["vrsceneOutput"]

        # This is also the input file for the render job
        first_file = self.format_output_filename(instance,
                                                 filename,
                                                 vrscene_output)

        start_frame = int(instance.data["startFrame"])
        end_frame = int(instance.data["endFrame"])

        # Primary job
        self.log.info("Submitting export job ..")

        payload = {
            "JobInfo": {
                # Top-level group name
                "BatchName": batch_name,

                # Job name, as seen in Monitor
                "Name": "Export {} [{}-{}]".format(task_name,
                                                   start_frame,
                                                   end_frame),

                # Arbitrary username, for visualisation in Monitor
                "UserName": deadline_user,

                "Plugin": "MayaBatch",
                "Frames": "{}-{}".format(start_frame, end_frame),
                "FramesPerTask": instance.data.get("framesPerTask", 1),

                "Comment": context.data.get("comment", ""),

                "OutputFilename0": os.path.dirname(first_file),
            },
            "PluginInfo": {

                # Renderer
                "Renderer": "vray",

                # Mandatory for Deadline
                "Version": cmds.about(version=True),

                # Input
                "SceneFile": filepath,

                "SkipExistingFrames": True,

                "UsingRenderLayers": True,

                "UseLegacyRenderLayers": True
            },

            # Mandatory for Deadline, may be empty
            "AuxFiles": []
        }

        # Include critical environment variables with submission + api.Session
        keys = [
            # Submit along the current Avalon tool setup that we launched
            # this application with so the Render Slave can build its own
            # similar environment using it, e.g. "maya2018;vray4.x;yeti3.1.9"
            "AVALON_TOOLS",
        ]
        environment = dict({key: os.environ[key] for key in keys
                            if key in os.environ}, **api.Session)

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        jobinfo_environment = self.build_jobinfo_environment(environment)

        payload["JobInfo"].update(jobinfo_environment)

        self.log.info("Job Data:\n{}".format(json.dumps(payload)))

        response = requests.post(url=deadline_url, json=payload)
        if not response.ok:
            raise RuntimeError(response.text)

        # Secondary job
        # Store job to create dependency chain
        dependency = response.json()

        if instance.data["suspendRenderJob"]:
            self.log.info("Skipping render job and publish job")
            return

        self.log.info("Submitting render job ..")

        start_frame = int(instance.data["startFrame"])
        end_frame = int(instance.data["endFrame"])
        ext = instance.data.get("ext",  "exr")

        # Create output directory for renders
        render_ouput = self.format_output_filename(instance,
                                                   filename,
                                                   instance.data["outputDir"],
                                                   dir=True)

        self.log.info("Render output: %s" % render_ouput)

        # Update output dir
        instance.data["outputDir"] = render_ouput

        # Format output file name
        sequence_filename = ".".join([instance.name, ext])
        output_filename = os.path.join(render_ouput, sequence_filename)

        # Ensure folder exists:
        if not os.path.exists(render_ouput):
            os.makedirs(render_ouput)

        payload_b = {
            "JobInfo": {

                "JobDependency0": dependency["_id"],
                "BatchName": batch_name,
                "Name": "Render {} [{}-{}]".format(task_name,
                                                   start_frame,
                                                   end_frame),
                "UserName": deadline_user,

                "Frames": "{}-{}".format(start_frame, end_frame),

                "Plugin": "Vray",
                "OverrideTaskExtraInfoNames": False,

                "OutputFilename0": render_ouput,
            },
            "PluginInfo": {

                "InputFilename": first_file,
                "OutputFilename": output_filename,
                "SeparateFilesPerFrame": True,
                "VRayEngine": "V-Ray",

                "Width": instance.data["resolution"][0],
                "Height": instance.data["resolution"][1],

            },
            "AuxFiles": [],
        }

        # Add vray renderslave to environment
        tools = environment["AVALON_TOOLS"] + ";vrayrenderslave"
        environment_b = deepcopy(environment)
        environment_b["AVALON_TOOLS"] = tools

        jobinfo_environment_b = self.build_jobinfo_environment(environment_b)
        payload_b["JobInfo"].update(jobinfo_environment_b)

        self.log.info(json.dumps(payload_b))

        # Post job to deadline
        response_b = requests.post(url=deadline_url, json=payload_b)
        if not response_b.ok:
            raise RuntimeError(response_b.text)

        # Add job for publish job
        if not instance.data.get("suspendPublishJob", False):
            instance.data["deadlineSubmissionJob"] = response_b.json()

    def build_command(self, instance):
        """Create command for Render.exe to export vray scene

        Args:
            instance

        Returns:
            str

        """

        cmd = ('-r vray -proj {project} -cam {cam} -noRender -s {startFrame} '
               '-e {endFrame} -rl {layer} -exportFramesSeparate')

        # Get the camera
        cammera = instance.data["cameras"][0]

        return cmd.format(project=instance.context.data["workspaceDir"],
                          cam=cammera,
                          startFrame=instance.data["startFrame"],
                          endFrame=instance.data["endFrame"],
                          layer=instance.name)

    def build_jobinfo_environment(self, env):
        """Format environment keys and values to match Deadline rquirements

        Args:
            env(dict): environment dictionary

        Returns:
            dict

        """
        return {"EnvironmentKeyValue%d" % index: "%s=%s" % (k, env[k])
                for index, k in enumerate(env)}

    def format_output_filename(self, instance, filename, template, dir=False):
        """Format the expected output file of the Export job

        Example:
            <Scene>/<Scene>_<Layer>/<Layer>
            "shot010_v006/shot010_v006_CHARS/CHARS"

        Args:
            instance:
            filename(str):
            dir(bool):

        Returns:
            str

        """

        def smart_replace(string, key_values):
            new_string = string
            for key, value in key_values.items():
                new_string = new_string.replace(key, value)
            return new_string

        # Ensure filename has no extension
        file_name, _ = os.path.splitext(filename)

        # Reformat without tokens
        output_path = smart_replace(template,
                                    {"<Scene>": file_name,
                                     "<Layer>": instance.name})

        if dir:
            return output_path.replace("\\", "/")

        start_frame = int(instance.data["startFrame"])
        filename_zero = "{}_{:04d}.vrscene".format(output_path, start_frame)

        result = filename_zero.replace("\\", "/")

        return result
