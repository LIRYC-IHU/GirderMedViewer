import asyncio
import logging
import sys
import traceback
from time import time

from trame_server.utils.asynchronous import create_task
from trame.app import get_server
from trame.widgets import gwc
from trame.widgets.vuetify2 import (VContainer, VRow, VCol,)
from .utils import FileDownloader, CacheMode
from ..utils import Button
from girder_client import GirderClient

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

server = get_server(client_type="vue2")
state, ctrl = server.state, server.controller


class GirderDrawer(VContainer):
    def __init__(self, quad_view, **kwargs):
        super().__init__(
            classes="fill-height pa-0",
            **kwargs
        )
        self.quad_view = quad_view
        self._build_ui()

    def _build_ui(self):
        with self:
            with VRow(
                style="height:100%",
                align_content="start",
                justify="center",
                no_gutters=True
            ):
                with VCol(cols=12):
                    GirderFileSelector(self.quad_view)

                with VCol(cols=12):
                    # TODO To Replace with ItemList
                    gwc.GirderDataDetails(
                        v_if=("detailed.length > 0",),
                        action_keys=("action_keys",),
                        value=("detailed",)
                    )
                with VCol(v_if=("displayed.length > 0",), cols="auto"):
                    Button(
                        tooltip="Clear View",
                        icon="mdi-close-box",
                        click=self.clear_views,
                        loading=("file_loading_busy",),
                        size=60,
                        disabled=("file_loading_busy",),
                    )

    def clear_views(self):
        self.quad_view.clear()
        state.displayed = []


class GirderFileSelector(gwc.GirderFileManager):
    def __init__(self, quad_view, **kwargs):
        state.selected_in_location = []
        super().__init__(
            v_if=("user",),
            v_model=("selected_in_location",),
            location=("location",),
            update_location=(self.update_location, "[$event]"),
            rowclick=(
                self.toggle_item,
                "[$event]"
            ),
            **kwargs
        )
        self.quad_view = quad_view
        girder_client = GirderClient(apiUrl=state.api_url)
        cache_mode = CacheMode(state.cache_mode) if state.cache_mode else CacheMode.No
        self.file_downloader = FileDownloader(girder_client, state.temp_dir, cache_mode)
        # FIXME do not use global variable
        global file_selector
        file_selector = self

        state.change("location", "displayed")(self.on_location_changed)
        state.change("api_url")(self.set_api_url)
        state.change("user")(self.set_user)

    def toggle_item(self, item):
        if item.get('_modelType') != 'item':
            return
        # Ignore double click on item
        clicked_time = time()
        if clicked_time - state.last_clicked < 1:
            return
        state.last_clicked = clicked_time
        is_selected = item in state.displayed
        logger.debug(f"Toggle item {item} selected={is_selected}")
        if is_selected:
            self.unselect_item(item)
        else:
            self.select_item(item)

    def update_location(self, new_location):
        """
        Called each time the user browse through the GirderFileManager.
        """
        logger.debug(f"Updating location to {new_location}")
        state.location = new_location

    def unselect_item(self, item):
        state.displayed = [i for i in state.displayed if i != item]
        self.quad_view.remove_data(item["_id"])

    def unselect_items(self):
        while len(state.displayed) > 0:
            self.unselect_item(state.displayed[0])

    def select_item(self, item):
        assert item.get('_modelType') == 'item', "Only item can be selected"

        state.displayed = state.displayed + [item]

        self.create_load_task(item)

    def create_load_task(self, item):
        logger.debug(f"Creating load task for {item}")
        state.file_loading_busy = True
        state.flush()

        async def load():
            await asyncio.sleep(1)
            try:
                self.load_item(item)
            finally:
                state.file_loading_busy = False
                state.flush()

        create_task(load())

    def load_item(self, item):
        logger.debug(f"Loading files {item}")
        try:
            logger.debug("Listing files")
            files = list(self.file_downloader.get_item_files(item))
            logger.debug(f"Files {files}")
            if len(files) != 1:
                raise Exception(
                    "No file to load. Please check the selected item."
                    if (not files) else
                    "You are trying to load more than one file. \
                    If so, please load a compressed archive."
                )
            with self.file_downloader.download_file(files[0]) as file_path:
                self.quad_view.load_files(file_path, item["_id"])
        except Exception:
            logger.error(f"Error loading file {item['_id']}: {traceback.format_exc()}")
            self.unselect_item(item)

    def set_api_url(self, api_url, **kwargs):
        logger.debug(f"Setting api_url to {api_url}")
        self.file_downloader.girder_client = GirderClient(apiUrl=api_url)

    def set_token(self, token):
        self.file_downloader.girder_client.setToken(token)

    def on_location_changed(self, **kwargs):
        logger.debug(f"Location/Displayed changed to {state.location}/{state.displayed}")
        location_id = state.location.get("_id", "") if state.location else ""
        state.selected_in_location = [item for item in state.displayed
                                      if item["folderId"] == location_id]
        state.detailed = state.selected_in_location if state.selected_in_location else [state.location]

    def set_user(self, user, **kwargs):
        logger.debug(f"Setting user to {user}")
        if user:
            state.location = state.default_location or user
            self.set_token(state.token)
        else:
            self.unselect_items()
            state.location = None
            self.set_token(None)
