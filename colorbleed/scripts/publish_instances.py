try:
    import colorbleed.lib
except ImportError as exc:
    # Ensure Deadline fails by output an error that contains "Fatal Error:"
    raise ImportError("Fatal Error: %s" % exc)

if __name__ == "__main__":
    # Perform remote publish with thorough error checking
    colorbleed.lib.publish_remote()
