import asyncio
from math import floor
import logging
import os
import sys
from time import time
from collections import defaultdict


from tempfile import TemporaryDirectory
from trame_server.utils.asynchronous import create_task
from trame.app import get_server
from trame.widgets import gwc, html, vtk
from trame.widgets.vuetify2 import (VContainer, VRow, VCol, VTooltip, Template,
                                    VBtn, VCard, VIcon)
from typing import Callable, Optional
from .vtk_utils import (
    create_rendering_pipeline,
    load_file,
    load_mesh,
    render_mesh_in_3D,
    render_mesh_in_slice,
    render_volume_in_3D,
    render_volume_in_slice,
    set_oblique_visibility
)

from girder_client import GirderClient

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

server = get_server(client_type="vue2")
state, ctrl = server.state, server.controller


# -----------------------------------------------------------------------------
# Viewer layout
# -----------------------------------------------------------------------------

file_selector = None

girder_client = GirderClient(apiUrl=state.api_url)

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
        is_mesh = item.get('name', '').endswith('.stl')
        # only 1 volume at a time for now
        if not is_mesh:
            self.unselect_items()

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
        with TemporaryDirectory() as tmp_dir:
            file_list = []
            logger.debug(f"Listing files")
            for file in girder_client.listFile(item["_id"]):
                file_path = os.path.join(tmp_dir, file["name"])
                logger.debug(f"Downloading {file_path}")
                girder_client.downloadFile(
                    file["_id"],
                    file_path
                )
                logger.debug(f"Downloaded {file_path}")
                file_list.append(file_path)

            if len(file_list) == 0:
                raise Exception(
                    "No file to load. Please check the selected item."
                )
            if len(file_list) > 1:
                raise Exception(
                    "You are trying to load more than one file. \
                    If so, please load a compressed archive."
                )
            file_path = file_list[0]
            try:
                self.quad_view.load_files(file_path, item["_id"])
            except Exception as e:
                logger.error(f"Error loading file {file_path}: {e}")
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

class Button():
    def __init__(
        self,
        *,
        tooltip: str,
        icon: str,
        icon_color: str = None,
        click: Optional[Callable] = None,
        size: int = 40,
        **kwargs,
    ) -> None:

        with VTooltip(
            tooltip,
            right=True,
            transition="slide-x-transition"
        ):
            with Template(v_slot_activator="{ on, attrs }"):
                with VBtn(
                    text=True,
                    rounded=0,
                    height=size,
                    width=size,
                    min_height=size,
                    min_width=size,
                    click=click,
                    v_bind="attrs",
                    v_on="on",
                    **kwargs,
                ):
                    VIcon(icon, size=floor(0.6 * size), color=icon_color)


class ToolsStrip(html.Div):
    def __init__(self, quad_view = None, **kwargs):
        super().__init__(
            classes="bg-grey-darken-4 d-flex flex-column align-center",
            **kwargs,
        )
        self.quad_view = quad_view

        with self:
            # FIXME use a unique button
            with html.Div(v_if=("display_obliques",),):
                Button(
                    tooltip="Hide obliques",
                    icon="mdi-eye-remove-outline",
                    click=lambda: self.quad_view.set_obliques_visibility(False),
                    disabled=("displayed.length === 0",)
                )

            with html.Div(v_else=True):
                Button(
                    tooltip="Show obliques",
                    icon="mdi-eye-outline",
                    click=lambda: self.quad_view.set_obliques_visibility(True),
                    disabled=("displayed.length === 0",),
                )

            Button(
                tooltip="Clear View",
                icon="mdi-reload",
                click=lambda: self.quad_view.remove_volume(),
                loading=("file_loading_busy",),
                disabled=("displayed.length === 0",)
            )

    def set_quad_view(self, quad_view):
        self.quad_view = quad_view

class ViewGutter(html.Div):
    def __init__(self, view=0):
        super().__init__(
            classes="gutter",
            style=(
                "position: absolute;"
                "top: 0;"
                "left: 0;"
                "background-color: transparent;"
                "height: 100%;"
            )
        )
        self.view = view
        with self:
            with html.Div(
                v_if=("displayed.length>0",),
                classes="gutter-content d-flex flex-column fill-height pa-2"
            ):
                Button(
                    tooltip="Reset View",
                    icon="mdi-camera-flip-outline",
                    icon_color="white",
                    click=self.reset_view,
                )

                Button(
                    v_if=("quad_view",),
                    tooltip="Extend to fullscreen",
                    icon="mdi-fullscreen",
                    icon_color="white",
                    click=self.extend_fullscreen,
                )

                Button(
                    v_else=True,
                    tooltip="Exit fullscreen",
                    icon="mdi-fullscreen-exit",
                    icon_color="white",
                    click=self.exit_fullscreen,
                )

    def reset_view(self):
        reslice_image = self.view.render_window.reslice_image
        if reslice_image:
            bounds = self.view.renderer.GetViewProps() \
                .GetLastProp() \
                .GetBounds()
            center = (
                (bounds[0] + bounds[1]) / 2.0,
                (bounds[2] + bounds[3]) / 2.0,
                (bounds[4] + bounds[5]) / 2.0
            )
            # Replace slice cursor at the volume center
            reslice_image.GetResliceCursor().SetCenter(center)
            reslice_image.GetResliceCursorWidget().ResetResliceCursor()
        else:
            self.view.renderer.GetActiveCamera().SetFocalPoint((0, 0, 0))
            self.view.renderer.GetActiveCamera().SetPosition((0, 0, 1))

        self.view.renderer.ResetCameraScreenSpace(0.8)
        self.view.render_window.Render()
        self.view.interactors.Render()

        ctrl.view_update()

    def extend_fullscreen(self):
        state.quad_view = False

    def exit_fullscreen(self):
        state.quad_view = True


class VtkView(vtk.VtkRemoteView):
    """ Base class for VTK views """
    def __init__(self, **kwargs):
        renderers, render_windows, interactors = create_rendering_pipeline(1)
        super().__init__(render_windows[0], **kwargs)
        self.renderer = renderers[0]
        self.render_window = render_windows[0]
        self.interactor = interactors[0]
        self.data = defaultdict(list)

    def register_data(self, data_id, data):
        # Associate data (typically an actor) to data_id so that it can be
        # removed when data_id is unregistered.
        self.data[data_id].append(data)

    def unregister_data(self, data_id, no_render=False):
        for data in self.data[data_id]:
            if data.IsA("vtkVolume"):
                self.renderer.RemoveVolume(data)
            elif data.IsA("vtkActor"):
                self.renderer.RemoveActor(data)
            elif data.IsA("vtkImageViewer2"):
                data.SetupInteractor(None)
                # FIXME: check for leak
                # data.SetRenderer(None)
                # data.SetRenderWindow(None)
        self.data.pop(data_id)
        if not no_render:
            self.update()


class SliceView(VtkView):
    """ Display volume as a 2D slice along a given axis """
    def __init__(self, axis, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis
        self._build_ui()
    
    def add_volume(self, image_data, data_id=None):
        reslice_image_viewer = render_volume_in_slice(
            data_id,
            image_data,
            self.renderer,
            self.axis,
            obliques=state.display_obliques
        )
        self.register_data(data_id, reslice_image_viewer)
        self.update()

    def add_mesh(self, poly_data, data_id=None):
        actor = render_mesh_in_slice(
            data_id,
            poly_data,
            self.renderer
        )
        self.register_data(data_id, actor)
        self.update()

    # FIXME: react to display_obliques change
    def set_obliques_visibility(self, visible):
        for reslice_image_viewers in self.data.values():
            for reslice_image_viewer in reslice_image_viewers:
                set_oblique_visibility(reslice_image_viewer, visible)
        self.update()

    def _build_ui(self):
        with self:
            ViewGutter(self)
            ctrl.view_update.add(self.update)
            ctrl.view_reset_camera.add(self.reset_camera)


class ThreeDView(VtkView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()
    
    def add_volume(self, image_data, data_id=None):
        volume = render_volume_in_3D(
            image_data,
            self.renderer
        )
        self.register_data(data_id, volume)
        self.update()
    
    def add_mesh(self, poly_data, data_id=None):
        actor = render_mesh_in_3D(
            poly_data,
            self.renderer
        )
        self.register_data(data_id, actor)
        self.update()

    def _build_ui(self):
        with self:
            ViewGutter(self)
            ctrl.view_update.add(self.update)
            ctrl.view_reset_camera.add(self.reset_camera)


class QuadView(VContainer):
    def __init__(self, **kwargs):
        super().__init__(
            classes="fill-height pa-0",
            **kwargs
        )
        self.twod_views = []
        self.threed_views = []
        self.views = []
        self._build_ui()

    def remove_data(self, data_id=None):
        for view in self.views:
            view.unregister_data(data_id)
        ctrl.view_update()

    def load_files(self, file_path, data_id=None):
        logger.debug(f"Loading file {file_path}")
        if file_path.endswith(".stl"):
            poly_data = load_mesh(file_path)
            for view in self.views:
                view.add_mesh(poly_data, data_id)
        else:
            image_data = load_file(file_path)
            for view in self.views:
                view.add_volume(image_data, data_id)

        ctrl.view_update()

    def set_obliques_visibility(self, visible):
        state.display_obliques = True
        for view in self.twod_views:
            view.set_obliques_visibility(visible)
        ctrl.view_update()

    def _build_ui(self):
        with self:
            with VRow(style="height:50%", no_gutters=True):
                with VCol(cols=6):
                    with SliceView(0) as sag_view:
                        self.twod_views.append(sag_view)
                        self.views.append(sag_view)
                with VCol(cols=6):
                    with ThreeDView() as threed_view:
                        self.threed_views.append(threed_view)
                        self.views.append(threed_view)

            with VRow(style="height:50%", no_gutters=True):
                with VCol(cols=6):
                    with SliceView(1) as cor_view:
                        self.twod_views.append(cor_view)
                        self.views.append(cor_view)
                with VCol(cols=6):
                    with SliceView(2) as ax_view:
                        self.twod_views.append(ax_view)
                        self.views.append(ax_view)

