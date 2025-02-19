import ast
import os
from urllib.parse import urljoin
from configparser import ConfigParser
import logging
import sys
from trame.app import get_server
from trame.decorators import TrameApp, change
from trame.widgets import gwc, html
from trame.ui.vuetify import SinglePageWithDrawerLayout
from trame.widgets.vuetify2 import (VTextField, VContainer, VCard, VDialog, VRow, VSpacer)
from .girder.components import GirderDrawer
from .vtk.components import QuadView, ToolsStrip
from .utils import Button, is_valid_url

# ---------------------------------------------------------
# Engine class
# ---------------------------------------------------------


@TrameApp()
class MyTrameApp:
    def __init__(self, server=None):
        self.server = get_server(server, client_type="vue2")

        self.load_config()
        self.configure_logs()

        self.state.trame__title = "GirderMedViewer"
        self.state.girder_connected = False
        self.state.obliques_visibility = True
        self.state.main_drawer = False
        self.state.user = None
        self.state.file_loading_busy = False
        self.state.displayed = []  # Items loaded and visible in the viewer
        self.state.detailed = []  # Items for which detailed information is displayed
        self.state.last_clicked = 0
        self.state.action_keys = [{"for": []}]

        self._build_ui()
        if self.server.hot_reload:
            self.server.controller.on_server_reload.add(self._build_ui)

    @property
    def state(self):
        return self.server.state

    @property
    def ctrl(self):
        return self.server.controller

    def load_config(self, config_file_path=None):
        """
        Load the configuration file app.cfg if any and set the state variables accordingly.
        If provided, app.cfg must at least contain girder/api_root.
        """
        if config_file_path is None:
            current_working_directory = os.getcwd()
            config_file_path = os.path.join(current_working_directory, "app.cfg")

        if os.path.exists(config_file_path) is False:
            return

        self.config = ConfigParser()
        self.config.read(config_file_path)

        self.state.girder_url = self.config.get("girder", "url", fallback=None)

        self.state.app_name = self.config.get("ui", "name", fallback="Girder Medical Viewer")

        self.state.temp_dir = self.config.get("download", "directory", fallback=None)
        self.state.cache_mode = self.config.get("download", "cache_mode", fallback=None)

    def get_girder_config(self, girder_url, config_key, **kwargs):
        """
        Load the girder configuration of the specified girder_url if it has been configured in the file app.cfg
        else load the default one ("girder").
        Accepts raw, vars and fallback as keyword arguments (RawConfigParser.get method).
        """
        return self.config.get(
            girder_url if girder_url in self.config else "girder",
            config_key, **kwargs
        )

    def connect_girder(self):
        self.provider = gwc.GirderProvider(
            value=self.state.api_url,
            trame_server=self.server
        )
        self.ctrl.provider_logout.add(self.provider.logout)
        self.provider.register_layout(self.ui)
        self.ui.flush_content()

    def disconnect_girder(self):
        # restore ui root to original root
        self.ui._current_root = self.ui._original_root
        self.ctrl.provider_logout.remove(self.provider.logout)
        del self.provider
        self.ui.flush_content()

    def configure_logs(self):
        log_level = self.config.get("logging", "log_level", fallback="INFO")
        logging.basicConfig(stream=sys.stdout)
        # Silence dependencies logs and keep only the application ones
        logging.getLogger().setLevel(logging.WARNING)
        logging.getLogger(__package__).setLevel(log_level)

    @change("girder_url")
    def set_girder_url(self, girder_url, **kwargs):
        if self.state.girder_connected:
            self.state.girder_connected = False
            self.state.default_location = {}
            self.disconnect_girder()

        if girder_url:
            api_root = self.get_girder_config(girder_url, "api_root")
            api_url = urljoin(
                girder_url,
                api_root
            )
            valid_url, self.state.girder_error = is_valid_url(api_url)
            if valid_url:
                self.state.api_url = api_url
                self.connect_girder()
                self.state.girder_connected = True
                self.state.default_location = ast.literal_eval(
                    self.get_girder_config(girder_url, "default_location", fallback="{}")
                )
                self.state.assetstore_dir = self.get_girder_config(
                    girder_url, "assetstore", fallback=None
                )
        else:
            self.state.girder_error = "URL required"

    @change("user")
    def set_user(self, user, **kwargs):
        self.state.user_name = f"{user.get('firstName', None)} {user.get('lastName', None)}" if user else None
        self.state.display_login_dialog = user is None
        self.state.main_drawer = user is not None

    def _build_ui(self, *args, **kwargs):
        with SinglePageWithDrawerLayout(
            self.server,
            show_drawer=False,
            width="400px"
        ) as self.ui:
            self.ui.title.set_text(self.state.app_name)
            self.ui.toolbar.height = 75

            with self.ui.toolbar, VRow(align="center", style="margin: 0px"):
                VSpacer()
                VTextField(
                    error_messages=("girder_error", None),
                    placeholder="Enter a Girder URL",
                    clearable=True,
                    v_model=("girder_input", self.state.girder_url),
                    change="girder_url = girder_input",
                    click_clear="girder_url = ''",
                    disabled=("user",),
                    style="max-width: 500px; margin: 20px"
                )
                VSpacer()
                Button(
                    v_if=("user",),
                    tooltip="Log out",
                    text="{{ user_name }}",
                    icon="mdi-logout",
                    large=True,
                    click=self.ctrl.provider_logout
                )
                Button(
                    v_if=("!user",),
                    text="Login",
                    icon="mdi-login",
                    large=True,
                    click="display_login_dialog = !display_login_dialog",
                    disabled=("!girder_connected",)
                )

            with self.ui.content:
                with html.Div(
                    v_if=("user",),
                    fluid=True,
                    classes="fill-height d-flex flex-row flex-grow-1"
                ):
                    ToolsStrip()
                    qd = QuadView()
                    self.quad_view = qd

            with self.ui.drawer:
                GirderDrawer(
                    self.quad_view,
                    v_if=("user",),
                )

            with VDialog(
                v_if=("!user && girder_connected",),
                v_model=("display_login_dialog",),
                max_width=500
            ), VCard(), VContainer():
                gwc.GirderAuthentication(
                    hide_forgot_password=True, register=False
                )
