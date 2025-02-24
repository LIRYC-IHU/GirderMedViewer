# GirderMedViewer

## Create environment and install dependencies
```
python -m venv env
source env/bin/activate
pip install -e ".[dev]"
```

## Setup configuration
To configure the application, create an `app.cfg` file based on the provided [app.template.cfg](./app.template.cfg). This configuration file allows you to:

- **UI Settings**: Customize the application title displayed in the toolbar.
- **Logging Configuration**: Define the logging level (e.g., `INFO` or `DEBUG`).
- **File Download Management**: Set up temporary storage for downloaded files.
- **Girder Connection**: Configure the API root and default connection settings.

By default, a standard Girder configuration is expected, but you can specify additional settings for predefined URLs if needed.

## Run trame application
```
girdermedviewer
```
You can add ```--server``` to your command line to prevent your browser from opening and ```--port``` to specifiy the port the server should listen to, default is 8080.
