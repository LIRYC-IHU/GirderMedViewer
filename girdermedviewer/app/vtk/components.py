import logging
import sys

from collections import defaultdict
from enum import Enum


from trame.app import get_server
from trame.widgets import html, vtk, client
from trame.widgets.vuetify2 import (VContainer, VCheckbox)
from ..utils import debounce, Button
from .utils import (
    create_rendering_pipeline,
    get_reslice_center,
    get_reslice_normals,
    load_mesh,
    load_volume,
    remove_prop,
    render_mesh_in_3D,
    render_mesh_in_slice,
    render_volume_as_overlay_in_slice,
    render_volume_in_3D,
    render_volume_in_slice,
    reset_reslice,
    reset_3D,
    set_oblique_visibility,
    set_reslice_center,
    set_window_level
)

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

server = get_server(client_type="vue2")
state, ctrl = server.state, server.controller


class ToolsStrip(html.Div):
    def __init__(self, **kwargs):
        super().__init__(
            classes="bg-grey-darken-4 d-flex flex-column align-center",
            **kwargs,
        )
        client.Style(".v-input--selection-controls__input {margin-right: 0px!important}")

        with self:
            VCheckbox(
                v_model=("obliques_visibility",),
                off_icon='mdi-eye-outline',
                on_icon='mdi-eye-remove-outline',
                color="black",
                disabled=("displayed.length === 0 || file_loading_busy",)
            )

            Button(
                tooltip="Reset Views",
                icon="mdi-camera-flip-outline",
                click=ctrl.reset,
                disabled=("displayed.length === 0 || file_loading_busy",)
            )


class ViewGutter(html.Div):
    def __init__(self, view, **kwargs):
        super().__init__(
            classes="gutter",
            style=(
                "position: absolute;"
                "top: 0;"
                "left: 0;"
                "background-color: transparent;"
                "height: 100%;"
            ),
            v_if=("displayed.length>0 && !file_loading_busy",),
            **kwargs
        )
        assert view.id is not None
        self.view = view
        with self:
            with html.Div(
                v_if=("displayed.length>0",),
                classes="gutter-content d-flex flex-column fill-height pa-2"
            ):
                Button(
                    tooltip=("{{ fullscreen==null ? 'Extend to fullscreen' : 'Exit fullscreen' }}",),
                    icon=("{{ fullscreen==null ? 'mdi-fullscreen' : 'mdi-fullscreen-exit' }}",),
                    icon_color="white",
                    click=self.toggle_fullscreen,
                )

    def toggle_fullscreen(self):
        state.fullscreen = None if state.fullscreen else self.view.id


class VtkView(vtk.VtkRemoteView):
    """ Base class for VTK views """
    def __init__(self, **kwargs):
        renderer, render_window, interactor = create_rendering_pipeline()
        super().__init__(render_window, interactive_quality=80, **kwargs)
        self.renderer = renderer
        self.render_window = render_window
        self.interactor = interactor
        self.data = defaultdict(list)
        ctrl.view_update.add(self.update)

    def get_data_id(self, data):
        return next((key for key, value in self.data.items() if data in value), None)

    def register_data(self, data_id, data):
        # Associate data (typically an actor) to data_id so that it can be
        # removed when data_id is unregistered.
        self.data[data_id].append(data)

    def unregister_data(self, data_id, no_render=False, only_data=None):
        for data in list(self.data[data_id]):
            if only_data is None or data == only_data:
                remove_prop(self.renderer, data)
                self.data[data_id].remove(data)
        if len(self.data[data_id]) == 0:
            self.data.pop(data_id)
        if not no_render:
            self.update()

    def unregister_all_data(self, no_render=False):
        data_ids = list(self.data.keys())
        for data_id in data_ids:
            self.unregister_data(data_id, True)
        if not no_render:
            self.update()


class Orientation(Enum):
    SAGITTAL = 0
    CORONAL = 1
    AXIAL = 2


class SliceView(VtkView):
    """ Display volume as a 2D slice along a given axis/orientation """
    ctrl.debounced_flush = debounce(0.3)(state.flush)

    def __init__(self, orientation, **kwargs):
        super().__init__(classes=f"slice {orientation.name.lower()}", **kwargs)
        self.orientation = orientation
        self._build_ui()

        state.change("position")(self.set_position)
        state.change("window_level")(self.set_window_level)
        ctrl.update_other_slice_views.add(self.update_from_other)
        ctrl.debounced_end_interaction.add(debounce(0.3)(self.end_interaction))

    def unregister_data(self, data_id, no_render=False, only_data=None):
        super().unregister_data(data_id, no_render=True, only_data=None)
        # we can't have secondary volumes without at least a primary volume
        if self.has_primary_volume() is False and self.has_secondary_volume():
            image_slice = self.get_image_slices()[0]
            secondary_data_id = self.get_data_id(image_slice)
            # Replace the secondary volume into a primary volume
            self.add_primary_volume(image_slice.GetMapper().GetDataSetInput(), secondary_data_id)
            super().unregister_data(secondary_data_id, True, only_data=image_slice)
        if not no_render:
            self.update()

    def get_reslice_image_viewers(self):
        return [obj for objs in self.data.values() for obj in objs if obj.IsA('vtkResliceImageViewer')]

    def get_image_slices(self):
        return [obj for objs in self.data.values() for obj in objs if obj.IsA('vtkImageSlice')]

    def update_from_other(self, other, interaction):
        """
        Rendering of the view being interacted with is already taken
        cared of automatically by the client side.
        Because interacting with the reslice cursor impacts the
        the other slice views, they must be updated client-side
        :param interaction True for StartInteraction or Interaction,
        False for EndInteraction, None for regular update.
        :type interaction bool or None
        """
        if self == other:
            return
        if interaction is True:
            # start_animation() no-op if already in animation
            # render with less quality than the currently interacted view 
            self.start_animation(fps=15, quality=int(self.interactive_quality / 3))
            self.update()
        elif interaction is False:
            self.stop_animation()  # does a high quality render
        else:  # interaction is None
            self.update()

    def end_interaction(self):
        self.update_from_other(None, False)

    def add_primary_volume(self, image_data, data_id=None):
        reslice_image_viewer = render_volume_in_slice(
            image_data,
            self.renderer,
            self.orientation.value,
            obliques=state.obliques_visibility
        )
        self.register_data(data_id, reslice_image_viewer)

        reslice_cursor_widget = reslice_image_viewer.GetResliceCursorWidget()
        reslice_image_viewer.AddObserver(
            'InteractionEvent', self.on_slice_scroll)
        reslice_cursor_widget.AddObserver(
            'InteractionEvent', self.on_reslice_cursor_interaction)
        reslice_cursor_widget.AddObserver(
            'EndInteractionEvent', self.on_reslice_cursor_end_interaction)
        reslice_image_viewer.GetInteractorStyle().AddObserver(
            'WindowLevelEvent', self.on_window_leveling)

        self.update()

    def add_secondary_volume(self, image_data, data_id=None):
        actor = render_volume_as_overlay_in_slice(
            image_data,
            self.renderer,
            self.orientation.value
        )
        self.register_data(data_id, actor)
        self.update()

    def has_primary_volume(self):
        return len(self.get_reslice_image_viewers()) > 0

    def has_secondary_volume(self):
        return len(self.get_image_slices()) > 0

    def add_volume(self, image_data, data_id=None):
        if self.has_primary_volume() is False:
            self.add_primary_volume(image_data, data_id)
        else:
            self.add_secondary_volume(image_data, data_id)

    def add_mesh(self, poly_data, data_id=None):
        actor = render_mesh_in_slice(
            poly_data,
            self.orientation.value,
            self.renderer
        )
        self.register_data(data_id, actor)
        self.update()

    def reset(self):
        for reslice_image_viewer in self.get_reslice_image_viewers():
            reset_reslice(reslice_image_viewer)
        self.update()

    def set_obliques_visibility(self, visible):
        for reslice_image_viewer in self.get_reslice_image_viewers():
            set_oblique_visibility(reslice_image_viewer, visible)
        self.update()

    def on_slice_scroll(self, reslice_image_viewer, event):
        """
        Triggered when scrolling the current image.
        It is the first way to modify the reslice cursor
        :see-also on_reslice_cursor_interaction
        """
        # Because it is called within a co-routine, position is not
        # flushed right away.
        state.position = get_reslice_center(reslice_image_viewer)
        ctrl.debounced_flush()

        ctrl.update_other_slice_views(self, interaction=True)
        ctrl.debounced_end_interaction()

    def on_reslice_cursor_interaction(self, reslice_image_widget, event):
        """
        Triggered when interacting with oblique lines.
        Because it is called within a co-routine, position is not flushed right away.
        """
        state.position = get_reslice_center(reslice_image_widget)
        state.normals = get_reslice_normals(reslice_image_widget)

        ctrl.update_other_slice_views(self, interaction=True)

    def on_reslice_cursor_end_interaction(self, reslice_image_widget, event):
        state.flush()  # flush state.position
        ctrl.update_other_slice_views(self, interaction=False)

    def on_window_leveling(self, interactor_style, event):
        # Because it is called within a co-routine, window_level is not
        # flushed right away.
        state.window_level = (
            interactor_style.GetCurrentImageProperty().GetColorWindow(),
            interactor_style.GetCurrentImageProperty().GetColorLevel())
        ctrl.debounced_flush()

        ctrl.update_other_slice_views(self, interaction=True)
        ctrl.debounced_end_interaction()

    def set_position(self, position, **kwargs):
        logger.debug(f"set_position: {position}")
        modified = False
        for reslice_image_viewer in self.get_reslice_image_viewers():
            modified = set_reslice_center(reslice_image_viewer, position) or modified
        if modified:
            self.update()

    def set_window_level(self, window_level, **kwargs):
        logger.debug(f"set_window_level: {window_level}")
        modified = False
        for reslice_image_viewer in self.get_reslice_image_viewers():
            modified = set_window_level(reslice_image_viewer, window_level) or modified
        if modified:
            self.update()

    def _build_ui(self):
        with self:
            ViewGutter(self)


class ThreeDView(VtkView):
    def __init__(self, **kwargs):
        super().__init__(classes="threed", **kwargs)
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

    def reset(self):
        reset_3D(self.renderer)
        self.update()

    def _build_ui(self):
        with self:
            ViewGutter(self)


class QuadView(VContainer):
    def __init__(self, **kwargs):
        super().__init__(
            classes="fill-height pa-0",
            fluid=True,
            **kwargs
        )
        self.views = []
        state.fullscreen = None
        self._build_ui()
        ctrl.reset = self.reset
        state.change("obliques_visibility")(self.set_obliques_visibility)

    @property
    def twod_views(self):
        return [view for view in self.views if isinstance(view, SliceView)]

    @property
    def threed_views(self):
        return [view for view in self.views if isinstance(view, ThreeDView)]

    def remove_data(self, data_id=None):
        for view in self.views:
            view.unregister_data(data_id)
        ctrl.view_update()

    def clear(self):
        for view in self.views:
            view.unregister_all_data()
        ctrl.view_update()

    def set_obliques_visibility(self, obliques_visibility, **kwargs):
        for view in self.twod_views:
            view.set_obliques_visibility(obliques_visibility)
        ctrl.view_update()

    def reset(self):
        for view in self.views:
            view.reset()
        ctrl.view_update()

    def load_files(self, file_path, data_id=None):
        logger.debug(f"Loading file {file_path}")
        if file_path.endswith(".stl"):
            poly_data = load_mesh(file_path)
            for view in self.views:
                view.add_mesh(poly_data, data_id)
        else:
            image_data = load_volume(file_path)
            for view in self.views:
                view.add_volume(image_data, data_id)

        ctrl.view_update()

    def _build_ui(self):
        with self:
            with html.Div(
                style=("""{
                       display: 'grid',
                       'grid-template-columns': fullscreen == null ? '1fr 1fr' : 'none',
                       gap: '2px',
                       width: '100%',
                       height: '100%',
                       position: 'relative'
                       }""",),
            ):
                with SliceView(Orientation.SAGITTAL,
                               id="sag_view",
                               v_if="fullscreen == null || fullscreen == 'sag_view'") as sag_view:
                    self.views.append(sag_view)
                with ThreeDView(id="threed_view",
                                v_if="fullscreen == null || fullscreen == 'threed_view'") as threed_view:
                    self.views.append(threed_view)
                with SliceView(Orientation.CORONAL, id="cor_view",
                               v_if="fullscreen == null || fullscreen == 'cor_view'") as cor_view:
                    self.views.append(cor_view)
                with SliceView(Orientation.AXIAL, id="ax_view",
                               v_if="fullscreen == null || fullscreen == 'ax_view'") as ax_view:
                    self.views.append(ax_view)
