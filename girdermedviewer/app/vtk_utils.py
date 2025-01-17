import logging
import sys

from vtkmodules.all import (
    vtkCommand,
    vtkRenderer,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkResliceImageViewer,
    vtkInteractorStyleImage,
    vtkWidgetEvent
)
from vtk import (
    vtkActor,
    vtkColorTransferFunction,
    vtkCutter,
    vtkImageReslice,
    vtkMatrix4x4,
    vtkNIFTIImageReader,
    vtkPiecewiseFunction,
    vtkPolyDataMapper,
    vtkResliceCursorLineRepresentation,
    vtkSmartVolumeMapper,
    vtkSTLReader,
    vtkTransform,
    vtkTransformFilter,
    vtkVolume,
    vtkVolumeProperty,
)

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# FIXME do not use global variable
# dict[axis:vtkResliceImageViewer]
viewers = dict()

def set_oblique_visibility(reslice_image_viewer, visible):
    reslice_cursor_widget = reslice_image_viewer.GetResliceCursorWidget()
    cursor_rep = vtkResliceCursorLineRepresentation.SafeDownCast(
        reslice_cursor_widget.GetRepresentation())
    reslice_cursor_actor = cursor_rep.GetResliceCursorActor()
    for axis in range(3):
        reslice_cursor_actor.GetCenterlineProperty(axis) \
            .SetOpacity(1.0 if visible else 0.0)
    reslice_cursor_widget.SetProcessEvents(visible)


def get_reslice_cursor(reslice_object):
    """
    Return the point where the 3 planes intersect.
    :rtype tuple[float, float, float]
    """
    if isinstance(reslice_object, vtkResliceImageViewer):
        reslice_object = reslice_object.GetResliceCursor()
    if reslice_object.IsA('vtkResliceCursorWidget'):
        reslice_object = reslice_object.GetResliceCursorRepresentation()
    if reslice_object.IsA('vtkResliceCursorRepresentation'):
        reslice_object = reslice_object.GetResliceCursor()
    assert reslice_object.IsA('vtkResliceCursor')
    return reslice_object


def get_reslice_center(reslice_object):
    """
    Return the point where the 3 planes intersect.
    :rtype tuple[float, float, float]
    """
    return get_reslice_cursor(reslice_object).center


def set_reslice_center(reslice_object, new_center):
    reslice_cursor = get_reslice_cursor(reslice_object)
    center = reslice_cursor.GetCenter()
    if (
            center[0] == new_center[0] and center[1] == center[1] and
            center[2] == new_center[2]):
        return False
    get_reslice_cursor(reslice_object).SetCenter(new_center)
    return True


def set_window_level(reslice_image_viewer, new_window_level):
    if (reslice_image_viewer.GetColorWindow() == new_window_level[0] and
            reslice_image_viewer.GetColorLevel() == new_window_level[1]):
        return False
    reslice_image_viewer.SetColorWindow(new_window_level[0])
    reslice_image_viewer.SetColorLevel(new_window_level[1])
    return True


def get_reslice_normals(reslice_object):
    """
    Return the 3 plane normals as a tuple of tuples.
    :rtype tuple[tuple[float, float, float],
                 tuple[float, float, float],
                 tuple[float, float, float]]
    """
    reslice_cursor = get_reslice_cursor(reslice_object)
    return (
        reslice_cursor.x_axis,
        reslice_cursor.y_axis,
        reslice_cursor.z_axis,
    )


def get_reslice_normal(reslice_image_viewer, axis):
    return get_reslice_normals(reslice_image_viewer)[axis]


def get_reslice_image_viewer(axis=-1):
    """
    Returns a matching reslice image viewer or create it if it does not exist.
    If axis is -1, it returns the firstly added reslice image viewer
    or create an axial (2) reslice image viewer if none exist.
    """
    if axis == -1:
        try:
            return next(iter(viewers.values()))
        except StopIteration:
            # no Reslice Image Viewer has been created for data_id
            axis = 2
    if axis in viewers:
        return viewers[axis]

    reslice_image_viewer = vtkResliceImageViewer()
    # is it the firstly created image viewer ?
    if len(viewers) == 0:
        reslice_cursor = get_reslice_cursor(reslice_image_viewer)
        reslice_cursor.GetPlane(0).SetNormal(-1, 0, 0)
        reslice_cursor.SetXViewUp(0, 0, -1)
        reslice_cursor.GetPlane(1).SetNormal(0, 1, 0)
        reslice_cursor.SetYViewUp(0, 0, -1)
        reslice_cursor.GetPlane(2).SetNormal(0, 0, -1)
        reslice_cursor.SetZViewUp(0, -1, 0)

    viewers[axis] = reslice_image_viewer

    return reslice_image_viewer


def render_volume_in_slice(image_data, renderer, axis=2, obliques=True):
    render_window = renderer.GetRenderWindow()
    interactor = render_window.GetInteractor()

    reslice_image_viewer = get_reslice_image_viewer(axis)

    reslice_image_viewer.SetRenderer(renderer)
    reslice_image_viewer.SetRenderWindow(render_window)
    reslice_image_viewer.SetupInteractor(interactor)
    reslice_image_viewer.SetInputData(image_data)

    # Set the reslice mode and axis
    # viewers[axis].SetResliceModeToOblique()
    reslice_image_viewer.SetSliceOrientation(axis)  # 0=X, 1=Y, 2=Z
    reslice_image_viewer.SetThickMode(0)

    reslice_cursor_widget = reslice_image_viewer.GetResliceCursorWidget()

    # (Oblique) Get widget representation
    cursor_rep = vtkResliceCursorLineRepresentation.SafeDownCast(
        reslice_cursor_widget.GetRepresentation()
    )

    # vtkResliceImageViewer instance share share the same lookup table
    reslice_image_viewer.SetLookupTable(get_reslice_image_viewer(-1).GetLookupTable())

    # (Oblique): Make all vtkResliceImageViewer instance share the same
    reslice_image_viewer.SetResliceCursor(get_reslice_image_viewer(-1).GetResliceCursor())
    for i in range(3):
        cursor_rep.GetResliceCursorActor() \
            .GetCenterlineProperty(i) \
            .SetLineWidth(4)
        cursor_rep.GetResliceCursorActor() \
            .GetCenterlineProperty(i)\
            .RenderLinesAsTubesOn()
        cursor_rep.GetResliceCursorActor() \
            .GetCenterlineProperty(i) \
            .SetRepresentationToWireframe()
        cursor_rep.GetResliceCursorActor() \
            .GetThickSlabProperty(i) \
            .SetRepresentationToWireframe()
    cursor_rep.GetResliceCursorActor() \
        .GetCursorAlgorithm() \
        .SetReslicePlaneNormal(axis)

    # (Oblique) Keep orthogonality between axis
    reslice_cursor_widget \
        .GetEventTranslator() \
        .RemoveTranslation(
            vtkCommand.LeftButtonPressEvent
        )
    reslice_cursor_widget \
        .GetEventTranslator() \
        .SetTranslation(
            vtkCommand.LeftButtonPressEvent, vtkWidgetEvent.Rotate
        )
    # Oblique
    reslice_image_viewer.SetResliceModeToOblique()

    if not obliques:
        set_oblique_visibility(reslice_image_viewer, obliques)

    # Fit volume to viewport
    renderer.ResetCameraScreenSpace(0.8)

    return reslice_image_viewer


def render_mesh_in_slice(poly_data, axis, renderer):
    reslice_image_viewer = get_reslice_image_viewer(axis)
    reslice_cursor = get_reslice_cursor(reslice_image_viewer)

    cutter = vtkCutter()
    cutter.SetInputData(poly_data)
    cutter.SetCutFunction(reslice_cursor.GetPlane(axis))

    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(cutter.GetOutputPort())

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1, 0, 0)

    renderer.AddActor(actor)
    renderer.ResetCameraScreenSpace(0.8)

    return actor


def render_volume_in_3D(image_data, renderer):
    volume_mapper = vtkSmartVolumeMapper()
    volume_mapper.SetInputData(image_data)

    # FIXME: does not work for all dataset
    volume_property = vtkVolumeProperty()
    volume_property.ShadeOn()
    volume_property.SetInterpolationTypeToLinear()

    color_function = vtkColorTransferFunction()
    color_function.AddRGBPoint(0, 0.0, 0.0, 0.0)  # Black
    color_function.AddRGBPoint(100, 1.0, 0.5, 0.3)  # Orange
    color_function.AddRGBPoint(255, 1.0, 1.0, 1.0)  # White

    opacity_function = vtkPiecewiseFunction()
    opacity_function.AddPoint(0, 0.0)  # Transparent
    opacity_function.AddPoint(100, 0.5)  # Semi-transparent
    opacity_function.AddPoint(255, 1.0)  # Opaque

    volume_property.SetColor(color_function)
    volume_property.SetScalarOpacity(opacity_function)

    volume = vtkVolume()
    volume.SetMapper(volume_mapper)
    volume.SetProperty(volume_property)

    renderer.AddVolume(volume)
    renderer.ResetCameraScreenSpace(0.8)

    return volume


def render_mesh_in_3D(poly_data, renderer):
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(poly_data)

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1, 0, 0)

    renderer.AddActor(actor)
    renderer.ResetCameraScreenSpace(0.8)

    return actor


def create_rendering_pipeline():
    renderer = vtkRenderer()
    render_window = vtkRenderWindow()
    interactor = vtkRenderWindowInteractor()

    render_window.AddRenderer(renderer)
    interactor.SetRenderWindow(render_window)
    interactor.GetInteractorStyle().SetCurrentStyleToTrackballCamera()

    renderer.ResetCamera()

    return renderer, render_window, interactor


def load_volume(file_path):
    """Read a file and return a vtkImageData object"""
    logger.debug(f"Loading volume {file_path}")
    if file_path.endswith((".nii", ".nii.gz")):
        reader = vtkNIFTIImageReader()
        reader.SetFileName(file_path)
        reader.Update()

        if reader.GetSFormMatrix() is None:
            return reader.GetOutput()

        transform = vtkTransform()
        transform.SetMatrix(reader.GetSFormMatrix())
        transform.Inverse()

        reslice = vtkImageReslice()
        reslice.SetInputConnection(reader.GetOutputPort())
        reslice.SetResliceTransform(transform)
        reslice.SetInterpolationModeToLinear()
        reslice.AutoCropOutputOn()
        reslice.TransformInputSamplingOff()
        reslice.Update()

        return reslice.GetOutput()

    raise Exception("File format is not handled for {}".format(file_path))


def load_mesh(file_path):
    """Read a file and return a vtkPolyData object"""
    logger.debug(f"Loading mesh {file_path}")
    if file_path.endswith(".stl"):
        reader = vtkSTLReader()
        reader.SetFileName(file_path)
        reader.Update()

        matrix = vtkMatrix4x4()
        matrix.SetElement(0, 0, -1)
        matrix.SetElement(1, 1, -1)

        transform = vtkTransform()
        transform.SetMatrix(matrix)
        transform.Inverse()

        transform_filter = vtkTransformFilter()
        transform_filter.SetInputConnection(reader.GetOutputPort())
        transform_filter.SetTransform(transform)
        transform_filter.Update()

        return transform_filter.GetOutput()

    raise Exception("File format is not handled for {}".format(file_path))
