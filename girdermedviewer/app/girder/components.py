import asyncio
import logging
import sys
import traceback
from time import time
from trame_server.utils.asynchronous import create_task
from trame.widgets import gwc, client
from trame.widgets.vuetify2 import (
    VContainer, VRow, VCol, VExpansionPanels, VExpansionPanel, VSlider,
    VExpansionPanelContent, VExpansionPanelHeader, VCard, VSubheader,
    VListItem, VList, VDivider, VAutocomplete
)
from .utils import FileDownloader, CacheMode, format_date
from ..utils import Button
from girder_client import GirderClient

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GirderDrawer(VContainer):
    def __init__(self, **kwargs):
        super().__init__(
            classes="girder-drawer fill-height pa-0",
            **kwargs
        )
        self._build_ui()

    def _build_ui(self):
        with self:
            with VRow(
                style="height:100%",
                align_content="start",
                justify="center",
                dense=True
            ):
                with VCol(cols=12):
                    GirderFileSelector()

                with VCol(v_if=("selected.length > 0",), cols=12):
                    GirderItemList()


class GirderFileSelector(gwc.GirderFileManager):
    def __init__(self, **kwargs):
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
        girder_client = GirderClient(apiUrl=self.state.api_url)
        cache_mode = CacheMode(self.state.cache_mode) if self.state.cache_mode else CacheMode.No
        self.file_downloader = FileDownloader(girder_client, self.state.temp_dir, cache_mode)

        self.state.change("location", "selected")(self.on_location_changed)
        self.state.change("api_url")(self.set_api_url)
        self.state.change("user")(self.set_user)

    def toggle_item(self, item):
        if item.get('_modelType') != 'item':
            return
        # Ignore double click on item
        clicked_time = time()
        if clicked_time - self.state.last_clicked < 1:
            return
        self.state.last_clicked = clicked_time
        is_selected = item in self.state.selected
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
        self.state.selected = [i for i in self.state.selected if i != item]
        self.ctrl.remove_data(item["_id"])

    def unselect_items(self):
        while len(self.state.selected) > 0:
            self.unselect_item(self.state.selected[0])

    def select_item(self, item):
        assert item.get('_modelType') == 'item', "Only item can be selected"
        item["humanCreated"] = format_date(item["created"], self.state.date_format)
        item["humanUpdated"] = format_date(item["updated"], self.state.date_format)
        item["parentMeta"] = self.file_downloader.get_item_inherited_metadata(item)
        item["loading"] = False
        item["loaded"] = False

        self.state.selected = self.state.selected + [item]

        self.create_load_task(item)

    def create_load_task(self, item):
        logger.debug(f"Creating load task for {item}")
        item["loading"] = True
        self.state.dirty("selected")
        self.state.flush()

        async def load():
            await asyncio.sleep(1)
            try:
                self.load_item(item)
            finally:
                item["loading"] = False
                item["loaded"] = True
                self.state.dirty("selected")
                self.state.flush()

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
                self.ctrl.load_files(file_path, item["_id"])
        except Exception:
            logger.error(f"Error loading file {item['_id']}: {traceback.format_exc()}")
            self.unselect_item(item)

    def set_api_url(self, api_url, **kwargs):
        logger.debug(f"Setting api_url to {api_url}")
        self.file_downloader.girder_client = GirderClient(apiUrl=api_url)

    def set_token(self, token):
        self.file_downloader.girder_client.setToken(token)

    def on_location_changed(self, **kwargs):
        logger.debug(f"Location/Selected changed to {self.state.location}/{self.state.selected}")
        location_id = self.state.location.get("_id", "") if self.state.location else ""
        self.state.selected_in_location = [item for item in self.state.selected
                                           if item["folderId"] == location_id]

    def set_user(self, user, **kwargs):
        logger.debug(f"Setting user to {user}")
        if user:
            self.state.location = self.state.default_location or user
            self.set_token(self.state.token)
        else:
            self.unselect_items()
            self.state.location = None
            self.set_token(None)


class GirderItemList(VCard):
    def __init__(self, **kwargs):
        super().__init__(
            **kwargs
        )
        client.Style(".v-expansion-panel-content__wrap { padding: 0 !important; };"
                     ".list-item {}")
        self._build_ui()

    def _build_ui(self):
        with self:
            with VExpansionPanels(focusable=True, multiple=True):
                GirderItemCard(
                    v_for="(item, i) in selected",
                    item="item",
                    index="i",
                )
            with VCol(cols="auto"):
                Button(
                    tooltip="Clear all",
                    icon="mdi-delete",
                    click=self.clear_views,
                )

    def clear_views(self):
        self.ctrl.clear()
        self.state.selected = []


class GirderItemCard(VExpansionPanel):
    def __init__(self, item, index, **kwargs):
        super().__init__(
            value=item,
            **kwargs
        )
        self.item = item
        self.index = index
        self._build_ui()

    def _build_ui(self):
        with self:
            with VExpansionPanelHeader(hide_actions=(f"!{self.item}.loaded",)):
                with VRow(align="center", justify="space-between", dense=True):
                    VCol("{{ " + self.item + ".name }}")
                    with VCol(classes="d-flex justify-end",):
                        Button(
                            tooltip="Delete item",
                            icon="mdi-delete",
                            loading=(f"{self.item}.loading",),
                            disabled=(f"{self.item}.loading",),
                            click_native_stop=(self.delete_item, f"[{self.item}._id]"),
                            __events=[("click_native_stop", "click.native.stop")]
                        )

            with VExpansionPanelContent(v_if=(f"{self.item}.loaded",)):
                # ItemSettings(self.item)
                ItemInfo(self.item)
                ItemMetadata(self.item)

    def delete_item(self, item_id):
        # redundant with GirdeFileSelector unselect_item
        self.state.selected = [i for i in self.state.selected if i["_id"] != item_id]
        self.ctrl.remove_data(item_id)


class ItemSettings(VCard):
    def __init__(self, item, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self._build_ui()

    def _build_ui(self):
        with self:
            with VList(dense=True, classes="pa-0"):
                with VRow(no_gutters=True):
                    with VCol(cols="auto"):
                        VSubheader("Opacity", classes="subtitle-1 font-weight-bold pl-4")
                    with VCol():
                        with VListItem():
                            VSlider(
                                # v_model=("opacity_{{item._id}}",),
                                min=0,
                                max=1,
                                step=0.05,
                                thumb_label=True
                            )
                with VRow(no_gutters=True):
                    with VCol(cols="auto"):
                        VSubheader("Preset", classes="subtitle-1 font-weight-bold pl-4")
                    with VCol():
                        with VListItem():
                            VAutocomplete()


class ItemInfo(VCard):
    def __init__(self, item, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self._build_ui()

    def _build_ui(self):
        with self:
            VSubheader("Info", classes="subtitle-1 font-weight-bold")
            with VList(dense=True, classes="pa-0"):
                VListItem("Size: {{ " + self.item + ".humanSize}}", classes="py-1 body-2")
                VListItem("Created on {{ " + self.item + ".humanCreated}}", classes="py-1 body-2")
                VListItem("Updated on {{ " + self.item + ".humanUpdated}}", classes="py-1 body-2")


class ItemMetadata(VCard):
    def __init__(self, item, **kwargs):
        super().__init__(**kwargs)
        self.item = item
        self._build_ui()

    def _build_ui(self):
        with self:
            VSubheader("Metadata", classes="subtitle-1 font-weight-bold pl-4")
            with VList(dense=True, classes="pa-0"):
                with VRow(no_gutters=True), VCol(
                    cols=6,
                    v_for=f"(value, key) in {self.item}.meta"
                ):
                    with VListItem(classes="fill-height py-1 body-2"):
                        with VRow(align="center", justify="space-between", no_gutters=True):
                            VCol(
                                "{{ key }}",
                                classes="shrink font-weight-bold"
                            )
                            VCol(
                                "{{ value }}",
                                classes="d-flex justify-end",
                                style="text-align: right"
                            )

                VDivider(
                    v_if=(f"Object.keys({self.item}.parentMeta).length > 0 && \
                          Object.keys({self.item}.meta).length > 0"))

                with VRow(no_gutters=True), VCol(
                    cols=6,
                    v_for=f"(value, key) in {self.item}.parentMeta",
                ):
                    with VListItem(classes="fill-height py-1 body-2"):
                        with VRow(align="center", justify="space-between", dense=True):
                            VCol(
                                "{{ key }}",
                                classes="shrink font-weight-bold"
                            )
                            VCol(
                                "{{ value }}",
                                classes="d-flex justify-end",
                                style="text-align: right"
                            )
