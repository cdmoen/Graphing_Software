"""
main.py - the Tkinter UI. Windows, widgets, the canvas, drawing, and animation timing.

All math lives in core.py and is reached with the `core.` prefix. The dependency only goes
one way: main imports core, core never imports main.
"""
import math
import tkinter as tk

import core
from core import GridConfig, GridPlane, Vector


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
    grid_step=2,
    segments=100,
    window_width=CANVAS_WIDTH,
    window_height=CANVAS_HEIGHT,
    scale=SCALE,
)

# The plane being displayed. Created here (math only, no canvas needed) so that anything below,
# including slider callbacks, can rely on it existing.
XY_grid = GridPlane(2, config, color="#fffb00")
XY_grid.name = "XY_grid"
XY_grid.tag = "XY_grid"
YZ_grid = GridPlane(0, config, color="#0F13FF")
YZ_grid.name = "YZ_grid"
YZ_grid.tag = "YZ_grid"
XZ_grid = GridPlane(1, config, color="#DC0BF8")
XZ_grid.name = "XZ_grid"
XZ_grid.tag = "XZ_grid"
# UI state: the most recently parsed function, kept so later features (a point that rides
# the curve, tangent lines) can evaluate it without re-parsing the text.
current_function = None


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

# ROTATION SLIDERS (one per axis, in degrees)
ROTATION_AXES = ("x", "y", "z")

rotation_frame = tk.Frame(root)
rotation_frame.pack(side="top", fill="x", padx=10)

rotation_sliders = {}
for axis_name in ROTATION_AXES:
    # `a=axis_name` binds the CURRENT value of the loop variable into each lambda. Without it,
    # every slider would use the last axis name, because the lambda looks the name up at call time.
    slider = tk.Scale(
        rotation_frame, from_=-180, to=180, orient="horizontal", length=250,
        label=f"Rotate {axis_name.upper()} (degrees)",
        command=lambda value, a=axis_name: on_rotation_slider(a, value),
    )
    slider.pack(side="left", padx=5)
    rotation_sliders[axis_name] = slider

tk.Button(rotation_frame, text="Reset", command=lambda: reset_rotation()).pack(side="left", padx=10)

canvas = tk.Canvas(root, bg="grey", width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
canvas.pack()
canvas.bind("<Button-1>", lambda e: handle_press(e))
canvas.bind("<B1-Motion>", lambda e: handle_mouse_drag(e))

is_dragging = False
drag_x = 0
drag_y = 0
x = 0
y = 0
def handle_press(event):
    global is_dragging, drag_x, drag_y
    drag_x = event.x
    drag_y = event.y
    print(f"click event x:  {event.x}  click y:  {event.y}")
    is_dragging = True

def handle_mouse_drag(event):
    global is_dragging, drag_x, drag_y, x, y
    print(f"drag_x: {drag_x}    drag_y: {drag_y}    x:  {x}    y: {y}  ")
    if is_dragging == True:
        x += int(-(event.x - drag_x))
        y += int(-(event.y - drag_y))
        on_rotation_slider("x", y)
        on_rotation_slider("y", x)
        drag_x = event.x
        drag_y = event.y



#######################
# DRAWING
#######################

def draw_grid(grid, config: GridConfig, color="blue", tag="grid", width=0):
    """Takes in a 2D list of grid line values, converts each point with core.to_pixel,
    and calls canvas.create_line to display them."""
    for line in grid:
        drawn_line = [core.to_pixel(point, config) for point in line]
        canvas.create_line(*drawn_line, fill=color, width=width, tags=tag)


def draw_plane(plane: GridPlane, show_axes=True):
    """Draws a GridPlane (replacing any previous drawing of it). The plane stores only math;
    this function is the part that knows about canvases."""
    canvas.delete(plane.tag)
    draw_grid(plane.u_lines, plane.config, plane.color, plane.tag)
    draw_grid(plane.v_lines, plane.config, plane.color, plane.tag)
    if show_axes:
        draw_grid(plane.axes, plane.config, plane.axis_color, plane.tag, width=3)
    canvas.tag_raise("function")    # keep any plotted curve on top of the grid


def draw_vector(vector: Vector, config: GridConfig):
    """Takes in a vector object and tells tkinter to draw it."""
    drawn_line = [core.to_pixel(point, config) for point in vector.points]
    canvas.create_line(*drawn_line, fill=vector.color, arrow=tk.LAST, width=2, tags=vector.tag)


def draw_function(points, *, color="red", width=0, config: GridConfig):
    drawn_function = [core.to_pixel(point, config) for point in points]
    canvas.create_line(*drawn_function, fill=color, width=width, tags="function")


#######################
# ANIMATION
#######################

def animate_grid_transform(starting_grid, ending_grid, config, steps=30, step_num=0, tag="grid", color="blue"):
    """
    Animates changes in coordinate grids. Draws each step of the animation by incrementing t
    and calling core.interpolate_between_coordinate_grids() for the current t value. Tkinter calls
    the function with a new t value each time until step_num reaches steps.
    Only items with the given tag are cleared each frame, so other things on the canvas stay put.
    """
    t = step_num / steps
    blended_grid = core.interpolate_between_coordinate_grids(starting_grid, ending_grid, t)
    canvas.delete(tag)
    draw_grid(blended_grid, config, color=color, tag=tag)

    if step_num < steps:
        root.after(2, animate_grid_transform, starting_grid, ending_grid, config, steps, step_num + 1, tag, color)


def animate_vector(start_vector: Vector, end_vector: Vector, config, steps=300, step_num=0):
    """
    Animates vector changes similar to how animate_grid_transform animates changes to the grid, but
    takes in whole vector objects. Creates a temporary 'blended vector' somewhere between start and end
    based on the current value of t. The temporary vector is tagged "temp" and deleted every frame,
    so only one copy is on screen at a time.
    """
    t = step_num / steps
    blended_points = core.interpolate_between_coordinate_grids([start_vector.points], [end_vector.points], t)[0]
    blended_vector = Vector.from_points(blended_points, config, color=start_vector.color)
    canvas.delete("temp")
    draw_vector(blended_vector, config)

    if step_num < steps:
        root.after(16, animate_vector, start_vector, end_vector, config, steps, step_num + 1)


#######################
# ROTATION CONTROLS
#######################

def on_rotation_slider(axis_name, degrees_text):
    global gridplanes
    """Called by a slider whenever it changes. A slider reports an ABSOLUTE angle (and as a string),
    so we replace that one axis's stored angle and leave the other two alone. The plane rotates its
    untouched base lines by the full stored angles every time, so nothing accumulates between events."""
    for i in gridplanes:
        angles = dict(zip(ROTATION_AXES, i.rotation))     # {"x": ..., "y": ..., "z": ...} in radians
        angles[axis_name] = math.radians(float(degrees_text))
        i.set_rotation(**angles)
        draw_plane(i)
        


def reset_rotation():
    """Setting a slider triggers its command, so this redraws as the sliders return to 0."""
    for slider in rotation_sliders.values():
        slider.set(0)


#######################
# PLOTTING A FUNCTION
#######################

def graph_function(expression, *, config: GridConfig = config):
    """Parses the text, plots it over the visible x range, and draws it. The grid is drawn once
    at startup, so only the previous curve is cleared here. The core raises errors; this
    function decides how to show them."""
    global current_function
    canvas.delete("function")
    status_var.set("")
    try:
        f = core.make_function(expression)
        x_min, x_max = core.visible_x_range(config)
        segments = core.plot_function(f, x_min, x_max, config)
    except Exception as error:      # bad user input shouldn't crash the app
        current_function = None
        status_var.set(f"Can't plot '{expression}': {error}")
        return
    current_function = f
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

gridplanes = [XY_grid, YZ_grid, XZ_grid]

draw_plane(XY_grid)
draw_plane(YZ_grid)
draw_plane(XZ_grid)

root.mainloop()
