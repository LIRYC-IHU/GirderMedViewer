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

## Deploy without launcher
```
python -m trame.tools.serve --exec girdermedviewer.app.core:MyTrameApp
```
This is not for production. It creates a unique process for multiple users.

## Deploy with wslink launcher
Create empty file "proxy-mapping.txt" and empty folder "logs".
Update examples/launcher/launcher.json and index.html to fix paths.

Start launcher:
```
python -m wslink.launcher .\examples\launcher\launcher.json --debug
```

Open launcher page at "localhost:9999"
