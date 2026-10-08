import tkinter as tk
import math
import sympy
from dataclasses import dataclass
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

# Lets users type "x^2" (exponent) and "2x" (implicit multiplication).
# sympy's default parser rejects both.
PARSE_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)


######################################
#           CLASSES
######################################

# CONFIG class for global values. Frozen, so nothing can accidentally change it.
@dataclass(frozen=True)
class GridConfig:
    grid_range: float
    grid_step: float
    segments: int
    window_width: int
    window_height: int
    scale: float


# Vector class for creating individual vectors
class Vector:
    def __init__(self, tip: tuple, config: GridConfig, origin: tuple = (0, 0, 0), color: str = "red", tag: str = "vector"):
        self.config = config
        self.origin = origin
        self.tip = tip
        self.color = color
        self.tag = tag
        self.points = construct_line(origin, tip, config.segments)

    def reconstruct(self):
        self.points = construct_line(self.origin, self.tip, self.config.segments)

    @classmethod
    def from_points(cls, points, config: GridConfig, color="red", tag="temp"):
        """Builds a vector from already-computed points (skips __init__).
        Defaults to the "temp" tag, which animate_vector deletes every frame."""
        new_vector = cls.__new__(cls)   # create instance without calling __init__
        new_vector.config = config
        new_vector.points = points
        new_vector.origin = points[0]
        new_vector.tip = points[-1]
        new_vector.color = color
        new_vector.tag = tag
        return new_vector


class GridPlane:
    """
    One flat grid plane (XY, XZ, or YZ) made of two families of lines.

    Naming: the plane's two in-plane axes are taken in x -> y -> z order with the
    fixed axis skipped, and called its 1st and 2nd axis:

        plane   fixed axis   1st axis   2nd axis
        XY      z            x          y
        XZ      y            x          z
        YZ      x            y          z

    u_lines run ALONG the 1st axis (the 2nd-axis coordinate is constant on each line).
    v_lines run ALONG the 2nd axis (the 1st-axis coordinate is constant on each line).
    On an XY plane, u_lines happen to be the horizontal lines and v_lines the vertical ones.

    State: the un-rotated lines are stored as "base" data. Rotation is stored as three
    angles and applied on demand, so changing origin/offset/divisions never loses the
    rotation, and the axes always rotate together with the grid.
    """

    def __init__(self, fixed_axis, config: GridConfig, color="blue", origin=0, offset=0, axis_color="black"):
        self.config = config
        self.color = color
        self.axis_color = axis_color
        self.fixed_axis = fixed_axis
        self.tag = "grid_plane"
        self._origin = origin      # shifts the grid centre within the plane (both in-plane axes)
        self._offset = offset      # where the plane sits along its fixed axis (for parallel sheets)
        self._divisions = generate_grid_divisions(config, origin)
        self._rotation = (0, 0, 0)  # angles (x, y, z), radians, applied about the world origin
        self.reconstruct()

    # ---- rotation -------------------------------------------------------
    def set_rotation(self, *, x=0, y=0, z=0):
        """Sets the plane's TOTAL rotation (radians), applied x, then y, then z.
        This sets rather than adds, so calling it twice with the same angles gives the same result."""
        self._rotation = (x, y, z)

    def _rotated(self, lines):
        if self._rotation == (0, 0, 0):
            return lines
        x, y, z = self._rotation
        return transform_grid_line_coordinates(lines, rotate_point, angle_x=x, angle_y=y, angle_z=z)

    # ---- line data (always reflects the current rotation) ---------------
    @property
    def u_lines(self):
        return self._rotated(self._base_u_lines)

    @property
    def v_lines(self):
        return self._rotated(self._base_v_lines)

    @property
    def axes(self):
        return self._rotated(self._base_axes)

    @property
    def lines(self):
        return self.u_lines + self.v_lines

    # ---- drawing --------------------------------------------------------
    def draw(self, show_axes=True):
        draw_grid(self.u_lines, self.config, self.color, self.tag)
        draw_grid(self.v_lines, self.config, self.color, self.tag)
        if show_axes:
            draw_grid(self.axes, self.config, self.axis_color, self.tag, width=3)

    # ---- building / syncing state ---------------------------------------
    def reconstruct(self):
        self._base_u_lines, self._base_v_lines = generate_grid_line_coordinates(
            self.config, self.fixed_axis, self._divisions, self._origin, self._offset)
        self._base_axes = self._build_axes()

    def _build_axes(self):
        """The two lines through the grid centre, one along each in-plane axis."""
        o = self._origin
        lo = o - self.config.grid_range
        hi = o + self.config.grid_range
        f = self._offset
        n = self.config.segments
        u_axis = construct_line(make_point(self.fixed_axis, lo, o, f), make_point(self.fixed_axis, hi, o, f), n)
        v_axis = construct_line(make_point(self.fixed_axis, o, lo, f), make_point(self.fixed_axis, o, hi, f), n)
        return [u_axis, v_axis]

    @property
    def origin(self):
        return self._origin

    @origin.setter
    def origin(self, new_origin):
        self._origin = new_origin
        self._divisions = generate_grid_divisions(self.config, new_origin)
        self.reconstruct()

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, new_offset):
        self._offset = new_offset
        self.reconstruct()

    @property
    def divisions(self):
        return self._divisions

    def set_custom_divisions(self, custom_divisions):
        self._divisions = custom_divisions
        self.reconstruct()


############################
# SETTING UP WINDOW
############################
root = tk.Tk()
root.title("Graphing Calculator")

# The canvas size is defined ONCE here, and config reads it from these constants.
SCALE = 20  # pixels per math unit
CANVAS_WIDTH = min(1000, int(root.winfo_screenwidth() * 0.9))
CANVAS_HEIGHT = min(800, int(root.winfo_screenheight() * 0.75))

config = GridConfig(
    grid_range=math.ceil(max(CANVAS_WIDTH, CANVAS_HEIGHT) / 2 / SCALE),  # just covers the visible area
    grid_step=1,
    segments=100,
    window_width=CANVAS_WIDTH,
    window_height=CANVAS_HEIGHT,
    scale=SCALE,
)

############################
# WIDGETS
############################

controls = tk.Frame(root)
controls.pack(side="top", fill="x", padx=10, pady=10)

# TEXT ENTRY
equation_entry_box = tk.Entry(controls, width=40)
equation_entry_box.pack(side="left")

# BUTTONS
# graph_function is defined further down; the lambda only looks it up when clicked.
equation_button = tk.Button(controls, text="Plot Graph", command=lambda: graph_function(equation_entry_box.get()))
equation_button.pack(side="left", padx=10)

# STATUS MESSAGES (errors show up here instead of the console)
status_var = tk.StringVar()
status_label = tk.Label(controls, textvariable=status_var, fg="red")
status_label.pack(side="left")

canvas = tk.Canvas(root, bg="white", width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
canvas.pack()


#############################
# HELPER FUNCTIONS
#############################

def construct_line(start: tuple[float, float, float], end: tuple[float, float, float], segments: int) -> list[tuple[float, float, float]]:
    """
    Takes in a start point, an end point (both (x, y, z) tuples), and the number of segments
    to divide the line into. Returns a list of (x, y, z) points tracing a straight path
    from start to end (segments + 1 points, endpoints included).
    """
    line = []
    for segment in range(segments + 1):
        t = segment / segments
        xcoord = start[0] + t * (end[0] - start[0])
        ycoord = start[1] + t * (end[1] - start[1])
        zcoord = start[2] + t * (end[2] - start[2])
        line.append((xcoord, ycoord, zcoord))

    return line


def make_point(fixed_axis: int, value_a: float, value_b: float, fixed_value: float = 0):
    """
    Builds a 3D point (x, y, z) for a plane where one axis is held at a fixed value.
    fixed_axis: which axis stays fixed (0=x, 1=y, 2=z)
    value_a, value_b: the two values to place on the other two axes, in x -> y -> z order
    fixed_value: the value held on the fixed axis (default 0)
    Example: make_point(2, 5, 7) holds Z fixed at 0, and fills in
    X=5, Y=7 (since x and y are axes 0 and 1) -> returns (5, 7, 0)
    Example: make_point(1, 5, 7, 3) holds Y at 3 -> returns (5, 3, 7)
    This lets one function build points for any of the three flat
    planes (XY, XZ, or YZ) just by changing which axis is 'fixed'
    """
    moving_axes = [axis for axis in range(3) if axis != fixed_axis]
    point = [0, 0, 0]
    point[fixed_axis] = fixed_value
    point[moving_axes[0]] = value_a
    point[moving_axes[1]] = value_b
    return tuple(point)


def translate_point(point: tuple, offset: tuple) -> tuple:
    """ Takes in any 3-value tuple and translates each value by the offset amount. All three
    points are offset by the same value.
    """
    x, y, z = point
    ox, oy, oz = offset
    return (x + ox, y + oy, z + oz)


def visible_x_range(config: GridConfig) -> tuple[float, float]:
    """The range of math-space x values that actually fit on the canvas."""
    half = config.window_width / 2 / config.scale
    return -half, half


#############################
# GRID MATRIX FUNCTIONS
#############################


def generate_grid_divisions(config: GridConfig, origin=0) -> list[float]:
    """
        Takes in value for size of grid (how far it stretches in every direction from the origin (0,0,0)), and the grid_step, meaning
        how many times is each axis subdivided, which determines gridline spacing. Returns a list of float values corresponding to the
        steps that would apply equally to all axes. Example: if range=5 & step=1, each axis would be [-5,-4, -3, -2, -1, 0, 1, 2, 3, 4, 5]
    """
    grid = [origin]
    v = config.grid_step
    while v <= config.grid_range:
        grid.append(origin + v)
        grid.append(origin - v)
        v += config.grid_step
    return sorted(grid)


def generate_grid_line_coordinates(config: GridConfig, fixed_axis: int, divisions=None, origin=0, offset=0):
    """
    Builds all the grid lines for one flat plane (XY, XZ, or YZ).

    config: grid settings (range, step, segments)
    fixed_axis: which axis is held fixed for this plane (0=x, 1=y, 2=z)
    divisions: positions of the lines (defaults to evenly spaced around origin)
    origin: shifts the grid centre within the plane
    offset: the value held on the fixed axis (lets you stack parallel planes)

    Returns (u_lines, v_lines), a TUPLE of two lists of lines.
    The plane's 1st and 2nd axes are the two non-fixed axes in x -> y -> z order
    (XY plane: x, y. XZ plane: x, z. YZ plane: y, z).
      u_lines: lines running ALONG the 1st axis (constant 2nd-axis coordinate)
      v_lines: lines running ALONG the 2nd axis (constant 1st-axis coordinate)

    Each line is a list of (x, y, z) points, so the shape of each returned list is:
    [
        [point, point, point, ...],   <- line 1
        [point, point, point, ...],   <- line 2
        ...
    ]
    Example: with fixed_axis=2 (XY plane) and grid_range=5, one u_line might be
    [(-5, 3, 0), (-4.9, 3, 0), ..., (5, 3, 0)] - a single line at y=3 running along x.
    """
    if divisions is None:
        divisions = generate_grid_divisions(config, origin)
    lo = origin - config.grid_range
    hi = origin + config.grid_range
    u_lines = []
    v_lines = []
    for d in divisions:
        # constant 2nd-axis coordinate d, sweeping the 1st axis
        u_start = make_point(fixed_axis, lo, d, offset)
        u_end = make_point(fixed_axis, hi, d, offset)
        u_lines.append(construct_line(u_start, u_end, config.segments))

        # constant 1st-axis coordinate d, sweeping the 2nd axis
        v_start = make_point(fixed_axis, d, lo, offset)
        v_end = make_point(fixed_axis, d, hi, offset)
        v_lines.append(construct_line(v_start, v_end, config.segments))
    return u_lines, v_lines


def transform_grid_line_coordinates(lines, callback, *args, **kwargs):
    """
    Takes in a 2D list of grid line coordinates of the shape generated by generate_grid_line_coordinates(),
    and performs the desired transform callback function on them, returning a new list of coordinates with the
    same shape. Receives *args and **kwargs and passes them to the callback.
    """
    new_lines = []
    for line in lines:
        new_line = []
        for point in line:
            new_point = callback(point, *args, **kwargs)
            new_line.append(new_point)
        new_lines.append(new_line)
    return new_lines


def rotate_point(point: tuple[float, float, float], *, angle_x: float = 0, angle_y: float = 0, angle_z: float = 0) -> tuple[float, float, float]:
    """Takes in a single point (x,y,z) and offsets its individual position to simulate
    the rotation of an entire grid around the x, y, or z axis (or all three). Can be called by
    transform_grid_line_coordinates() to rotate an entire 3d grid.
    Reminder: rotation is not commutative. Rotates first around X axis, then Y axis, and finally
    Z axis. Order of operations cannot be specified when calling the function.
    """
    x, y, z = point

    # Rotate around the X-axis first
    cos_x, sin_x = math.cos(angle_x), math.sin(angle_x)
    y1 = y * cos_x - z * sin_x
    z1 = y * sin_x + z * cos_x
    x1 = x  # x doesn't change when rotating around the x-axis

    # Then rotate the result around the Y-axis
    cos_y, sin_y = math.cos(angle_y), math.sin(angle_y)
    x2 = x1 * cos_y + z1 * sin_y
    z2 = -x1 * sin_y + z1 * cos_y
    y2 = y1  # y doesn't change when rotating around the y-axis

    # Then rotate around the Z-axis
    cos_z, sin_z = math.cos(angle_z), math.sin(angle_z)
    x3 = x2 * cos_z - y2 * sin_z
    y3 = x2 * sin_z + y2 * cos_z
    z3 = z2
    return (x3, y3, z3)


def generate_3d_grid(config: GridConfig):
    """ calls generate_grid_line_coordinates three times, once for each XY, XZ, and YZ plane.
    Creates list containing grid lines for three planes that all intersect at the origin (0,0,0)
    """
    all_lines = []
    for fixed_axis in range(3):
        u_lines, v_lines = generate_grid_line_coordinates(config, fixed_axis)
        all_lines.extend(u_lines)
        all_lines.extend(v_lines)
    return all_lines


#############################
# INTERPOLATION
#############################
def interpolate(pointA: float, pointB: float, t):
    """Takes in two single values and interpolates between them based on the current
    value of t. Called by interpolate_tuple()
    """
    newA = (1 - t) * pointA + t * pointB
    return newA


def interpolate_tuple(start: tuple, end: tuple, t):
    """Takes in 2 tuples of (x,y,z) values and calls interpolate() for the corresponding values
    of each tuple. Returns an interpolated tuple somewhere between start and end based on current
    value of t. Used for animation.
    """
    x1, y1, z1 = start
    x2, y2, z2 = end
    interpolated_x = interpolate(x1, x2, t)
    interpolated_y = interpolate(y1, y2, t)
    interpolated_z = interpolate(z1, z2, t)
    interpolated_tuple = (interpolated_x, interpolated_y, interpolated_z)
    return interpolated_tuple


def interpolate_between_coordinate_grids(grid1, grid2, t):
    """Interpolates between two flat coordinate planes (not an entire 3D matrix), by calling
    interpolate(tuple) for each corresponding point of the two grids. Returns a 'blended grid' that is
    somewhere between grid1 and grid2 depending on the current value of t. Used for animation.
    """
    blended_grid = []
    for line1, line2 in zip(grid1, grid2):
        blended_line = []
        for coordinate1, coordinate2 in zip(line1, line2):
            blended_coordinate = interpolate_tuple(coordinate1, coordinate2, t)
            blended_line.append(blended_coordinate)
        blended_grid.append(blended_line)
    return blended_grid


##############################
# VECTOR FUNCTIONS
##############################

# HELPERS

def shift_vector_tip(vector: Vector, x_shift=0, y_shift=0, z_shift=0):
    """Helper function for creating a new vector with a different tip location
    while keeping the vector origin, color, and tag the same
    """
    x, y, z = vector.tip
    new_tip = (x + x_shift, y + y_shift, z + z_shift)
    return Vector(new_tip, vector.config, origin=vector.origin, color=vector.color, tag=vector.tag)


#######################
# ANIMATION AND DRAWING
#######################

# HELPERS
def to_pixel(point: tuple, config: GridConfig) -> tuple:
    """Takes in the pure mathematical values for a point and returns values that can be
     used to display the point in the appropriate place on the screen
    """
    x, y, z = point
    px = config.window_width / 2 + (x * config.scale)
    py = config.window_height / 2 - (y * config.scale)
    return px, py


# DRAWING AND ANIMATING GRID LINES
def draw_grid(grid, config: GridConfig, color="blue", tag="grid", width=0):
    """Takes in 2D list of grid line values, translates them to usable display values by calling
     to_pixel, and then and calls tkinter method canvas.create_line to display them on the screen
    """
    for line in grid:
        drawn_line = [to_pixel(point, config) for point in line]
        canvas.create_line(*drawn_line, fill=color, width=width, tags=tag)


def animate_grid_transform(starting_grid, ending_grid, config, steps=30, step_num=0, tag="grid", color="blue"):
    """
    Animates changes in coordinate grids. Draws each step of the animation by incrementing t
    and calling interpolate_between_coordinate_grids() for the current t value. Tkinter calls the function
    with a new t value each time until the step_num reaches the desired steps value.
    Only items with the given tag are cleared each frame, so other things on the canvas stay put.
    """
    t = step_num / steps
    blended_grid = interpolate_between_coordinate_grids(starting_grid, ending_grid, t)
    canvas.delete(tag)
    draw_grid(blended_grid, config, color=color, tag=tag)

    if step_num < steps:
        root.after(2, animate_grid_transform, starting_grid, ending_grid, config, steps, step_num + 1, tag, color)


# DRAWING AND ANIMATING VECTORS
def draw_vector(vector: Vector, config: GridConfig):
    """Takes in a vector object and tells tkinter to draw it."""
    drawn_line = [to_pixel(point, config) for point in vector.points]
    canvas.create_line(*drawn_line, fill=vector.color, arrow=tk.LAST, width=2, tags=f"{vector.tag}")


def animate_vector(start_vector: Vector, end_vector: Vector, config, steps=300, step_num=0):
    """
    Animates vector changes similar to how animate_grid_transform animates changes to the grid. But
    takes in whole vector objects instead of lists of points. Creates a temporary 'blended vector' object that
    is somewhere between start and end vector based on current value of t. The temporary vector is tagged
    "temp" and deleted every frame, so only one copy is on screen at a time.
    """
    t = step_num / steps
    blended_points = interpolate_between_coordinate_grids([start_vector.points], [end_vector.points], t)[0]
    blended_vector = Vector.from_points(blended_points, config, color=start_vector.color)
    canvas.delete("temp")
    draw_vector(blended_vector, config)

    if step_num < steps:
        root.after(16, animate_vector, start_vector, end_vector, config, steps, step_num + 1)


# DRAWING AND ANIMATING FUNCTIONS
MAX_DEPTH = 16        # hard stop so recursion always terminates
FLATNESS_PX = 1.0     # refine until the curve is within ~1 pixel of straight


def make_function(expression: str):
    """Parse once and convert to a fast, ordinary Python function of x."""
    x = sympy.Symbol('x')
    parsed = parse_expr(expression, transformations=PARSE_TRANSFORMS)
    if parsed.free_symbols - {x}:
        raise ValueError("expression can only use the variable x")
    return sympy.lambdify(x, parsed, "math")


def safe_eval(f, x):
    """Return f(x) as a float, or None if it's undefined there."""
    try:
        y = float(f(x))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    if math.isnan(y) or math.isinf(y):
        return None
    return y


def refine(f, x0, y0, x1, y1, config, depth=0):
    """
    Returns the points AFTER x0, up to and including x1, as a list of
    (x, y) tuples. A None entry marks a gap (undefined region).
    y0 / y1 may be None if f is undefined at that endpoint.
    """
    end = [None if y1 is None else (x1, y1)]

    if depth >= MAX_DEPTH:
        # tiny interval with a huge jump between defined ends: a discontinuity
        if y0 is not None and y1 is not None:
            if abs(y1 - y0) * config.scale > config.window_height:
                return [None] + end
        return end

    if y0 is None and y1 is None:
        return end

    # Stop once the defined endpoints are well off-screen. Nothing further
    # in that direction is visible, so more samples would be wasted.
    limit = 2 * config.window_height / config.scale
    defined = [y for y in (y0, y1) if y is not None]
    if all(abs(y) > limit for y in defined):
        opposite_sides = len(defined) == 2 and (y0 > 0) != (y1 > 0)
        if not opposite_sides:      # opposite sides could be an asymptote jump
            return end

    xm = (x0 + x1) / 2
    ym = safe_eval(f, xm)

    # All three defined: is the midpoint close enough to the straight chord?
    if y0 is not None and y1 is not None and ym is not None:
        if abs(ym - (y0 + y1) / 2) * config.scale < FLATNESS_PX:
            return end

    return (refine(f, x0, y0, xm, ym, config, depth + 1)
            + refine(f, xm, ym, x1, y1, config, depth + 1))


def plot_function(expression, x_min, x_max, config=config):
    """Returns a list of segments; each segment is a list of (x, y, 0) points."""
    f = make_function(expression)
    n = config.segments

    xs = [x_min + i * (x_max - x_min) / n for i in range(n + 1)]
    ys = [safe_eval(f, x) for x in xs]

    items = [None if ys[0] is None else (xs[0], ys[0])]
    for i in range(n):
        items += refine(f, xs[i], ys[i], xs[i + 1], ys[i + 1], config)

    # split the flat list wherever a None gap marker appears
    segments, current = [], []
    for item in items:
        if item is None:
            if len(current) > 1:
                segments.append(current)
            current = []
        else:
            current.append((item[0], item[1], 0))
    if len(current) > 1:
        segments.append(current)
    return segments


def draw_function(points, *, color="red", width=0, config=config):
    drawn_function = [to_pixel(point, config) for point in points]
    canvas.create_line(*drawn_function, fill=color, width=width, tags="function")


def graph_function(expression, *, config=config):
    """Plots the expression over the visible x range. The grid is drawn once at startup,
    so only the previous curve is cleared here."""
    canvas.delete("function")
    status_var.set("")
    x_min, x_max = visible_x_range(config)
    try:
        segments = plot_function(expression, x_min, x_max, config)
    except Exception as error:      # bad user input shouldn't crash the app
        status_var.set(f"Can't plot '{expression}': {error}")
        return
    if not segments:
        status_var.set("Nothing to plot in this range")
        return
    for segment in segments:
        draw_function(segment, color="red", width=2, config=config)
    canvas.tag_raise("function")    # keep the curve on top of the grid


#############################
# STARTUP
#############################
equation_entry_box.bind("<Return>", lambda event: graph_function(equation_entry_box.get()))

XY_grid = GridPlane(2, config, color="#d9d9d9")
XY_grid.draw()

root.mainloop()
