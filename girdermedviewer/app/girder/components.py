import asyncio
import logging
import traceback
from time import time

from trame_server.utils.asynchronous import create_task
from trame.widgets import gwc, trame
from trame.widgets.vuetify2 import (VContainer, VRow, VCol, VTextField,)
from .utils import FileDownloader, CacheMode
from ..utils import Button
from girder_client import GirderClient

logger = logging.getLogger(__name__)
GIRDER_ID_HINT = 'Please provide an ID.'


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
                align_content="start",
                justify="center",
                no_gutters=True,
                classes='py-1'
            ):
                with VCol(cols=12):
                    VTextField(
                            label=('girder_id_label', 'Folder ID / URL'),
                            v_model=("girder_id_input", None),
                            autofocus=True,
                            persistent_hint=True,
                            hint=('girder_id_hint', GIRDER_ID_HINT),
                            dense=True,
                            outlined=True,
                            classes="py-1 px-1",
                            error=('girder_id_error', False),
                            success=('girder_id_success', False),
                            append_icon='mdi-refresh',
                            click_append=self.ctrl.reload_girder_id,
                            )

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
        self.state.displayed = []


class GirderFileSelector(gwc.GirderFileManager):
    def __init__(self, quad_view, **kwargs):
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
        self.state.selected_in_location = []
        self.quad_view = quad_view
        girder_client = GirderClient(apiUrl=self.state.api_url)
        cache_mode = CacheMode(self.state.cache_mode) if self.state.cache_mode else CacheMode.No
        self.file_downloader = FileDownloader(girder_client, self.state.temp_dir, cache_mode)
        # FIXME do not use global variable
        global file_selector
        file_selector = self

        self.state.change("location", "displayed")(self.on_location_changed)
        self.state.change("api_url")(self.set_api_url)
        self.state.change("user")(self.set_user)

        self.callback()
        self.ctrl.reload_girder_id = self.reload_girder_id

        self.state.url = ''
        # setup  client side function to catch the input url
        client_triggers = trame.ClientTriggers(
            ref="client_triggers",
            method1="url=window.location.href",
        )
        self.ctrl.call = client_triggers.call
        self.ctrl.on_client_connected.add(self.on_client_connected) # make it automnatic


    def on_client_connected(self, *args, **kwargs):
        """ Check for and load the id in input url.
        """
        self.ctrl.call('method1')
        # url reading in ctrl.call, won't be done at called time
        # use async to launch state change afterward.
        async def _load_url(): 
            while not self.file_downloader.girder_client.token: # wait at login screen
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)
            if self.state.url.split('/')[-1] != 'index.html':
                self.state.girder_id_input = self.state.url
            else:
                self.state.girder_id_input = ''
            self.state.flush()
        create_task(_load_url())

    def reload_girder_id(self,):
        """
        """
        self.state.dirty('girder_id_input')

    def callback(self,):
        """
        """
        @self.state.change('girder_id_input')
        def on_girder_id_input_changed(girder_id_input, **kwargs):
            """ Find compatible folder ID from the VTextField box.
            """
            if girder_id_input in [None, '']:
                # reset success state
                self.state.girder_id_hint = GIRDER_ID_HINT
                self.state.girder_id_error = False 
                self.state.girder_id_success = False

            else:
                # make it works with whole url
                if '/' in girder_id_input:
                    girder_id_input = girder_id_input.split('/')[-1]
                self.state.girder_id_input = girder_id_input

                try: 
                    ## try loading id as folder
                    location = self.file_downloader.girder_client.getFolder(girder_id_input)
                    self.update_location(location)

                    # change location success
                    self.state.girder_id_error = False
                    self.state.girder_id_success = True
                    self.state.girder_id_hint = "Click ⟳ to reload ID."

                except:
                    # try loading id as item, then get parent folder 
                    try:
                        item = self.file_downloader.girder_client.getItem(girder_id_input)
                        folder_id = item['folderId']
                        location = self.file_downloader.girder_client.getFolder(folder_id)
                        self.update_location(location)

                        # change location success
                        self.state.girder_id_error = False
                        self.state.girder_id_success = True
                        self.state.girder_id_hint = "Click ⟳ to reload ID."

                        ## Auto select files
                        # # self.state.flush()
                        # async def select_item():
                        #     await asyncio.sleep(1)
                        #     self.select_item(item)
                        #     self.state.flush()
                        # # self.select_item(item)
                        # create_task(select_item())

                    except:
                        self.state.girder_id_error = True
                        self.state.girder_id_success = False
                        self.state.girder_id_hint = "Error loading ID, click ⟳ to retry."


    def toggle_item(self, item):
        if item.get('_modelType') != 'item':
            return
        # Ignore double click on item
        clicked_time = time()
        if clicked_time - self.state.last_clicked < 1:
            return
        self.state.last_clicked = clicked_time
        is_selected = item in self.state.displayed
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
        self.state.location = new_location

    def unselect_item(self, item):
        self.state.displayed = [i for i in self.state.displayed if i != item]
        self.quad_view.remove_data(item["_id"])

    def unselect_items(self):
        while len(self.state.displayed) > 0:
            self.unselect_item(self.state.displayed[0])

    def select_item(self, item):
        assert item.get('_modelType') == 'item', "Only item can be selected"

        self.state.displayed = self.state.displayed + [item]

        self.create_load_task(item)

    def create_load_task(self, item):
        logger.debug(f"Creating load task for {item}")
        self.state.file_loading_busy = True
        self.state.flush()

        async def load():
            await asyncio.sleep(1)
            try:
                self.load_item(item)
            finally:
                self.state.file_loading_busy = False
                self.state.flush()

        create_task(load())

    def load_item(self, item):
        logger.debug(f"Loading item {item}")
        try:
            files = list(self.file_downloader.get_item_files(item))
            logger.debug(f"Files to load: {files}")
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
        logger.debug(f"Location/Displayed changed to {self.state.location}/{self.state.displayed}")
        location_id = self.state.location.get("_id", "") if self.state.location else ""
        self.state.selected_in_location = [item for item in self.state.displayed
                                           if item["folderId"] == location_id]
        self.state.detailed = self.state.selected_in_location if self.state.selected_in_location else [self.state.location]

    def set_user(self, user, **kwargs):
        logger.debug(f"Setting user to {user}")
        if user:
            self.state.location = self.state.default_location or user
            self.set_token(self.state.token)
        else:
            self.unselect_items()
            self.state.location = None
            self.set_token(None)
