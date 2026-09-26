from pydualsense import pydualsense
from utils import write_limited_rows


prev_gyro = [0., 0., 0.]
prev_rstick = [0., 0.]
prev_lstick = [0., 0.]
prev_acc = [0., 0., 0.]


def check_by_change(prev_val, val, threshold, name, val_format):
    change = sum((pv - v) ** 2 for pv, v in zip(prev_val, val))
    if change > threshold:
        write_limited_rows(f"{name}: change={change:.3f}, {val_format % tuple(val)}, prev_gyro=({val_format % tuple(prev_val)})")


def bind_bool_event(event, name):
    def handler(state):
        write_limited_rows(f"{name}: {'pressed' if state else 'released'}")

    event += handler


def on_left_stick(x, y):
    global prev_lstick
    new_lstick = [x, y]
    check_by_change(prev_lstick, new_lstick, 100, 'left stick', 'x=%.2f, y=%.2f')
    prev_lstick = new_lstick


def on_right_stick(x, y):
    global prev_rstick
    new_rstick = [x, y]
    check_by_change(prev_rstick, new_rstick, 100, 'right stick', 'x=%.2f, y=%.2f')
    prev_rstick = new_rstick


def on_gyro(pitch, yaw, roll):
    global prev_gyro
    new_gyro = [pitch, yaw, roll]
    check_by_change(prev_gyro, new_gyro, 50000, 'gyro', 'pitch=%.2f, yaw=%.2f, roll=%.2f')
    prev_gyro = new_gyro


def on_accel(X, Y, Z):
    global prev_acc
    new_acc = [X, Y, Z]
    check_by_change(prev_acc, new_acc, 100, 'accelerometer', 'X=%.2f, Y=%.2f, Z=%.2f')
    prev_acc = new_acc


def on_l1(state):
    write_limited_rows(f"L1: {'pressed' if state else 'released'}")


def on_l2(value):
    write_limited_rows(f"L2 value: {value}")


def on_r1(state):
    write_limited_rows(f"R1: {'pressed' if state else 'released'}")


def on_r2(value):
    write_limited_rows(f"R2 value: {value}")


def check_controls():
    ds = pydualsense()
    ds.init()

    # Face buttons
    bind_bool_event(ds.cross_pressed, "cross")
    bind_bool_event(ds.circle_pressed, "circle")
    bind_bool_event(ds.square_pressed, "square")
    bind_bool_event(ds.triangle_pressed, "triangle")

    # D-pad
    bind_bool_event(ds.dpad_up, "dpad_up")
    bind_bool_event(ds.dpad_down, "dpad_down")
    bind_bool_event(ds.dpad_left, "dpad_left")
    bind_bool_event(ds.dpad_right, "dpad_right")

    # Shoulder / stick buttons
    bind_bool_event(ds.l1_changed, "l1")
    bind_bool_event(ds.r1_changed, "r1")
    bind_bool_event(ds.l3_changed, "l3")
    bind_bool_event(ds.r3_changed, "r3")

    # System buttons
    bind_bool_event(ds.ps_pressed, "ps")
    bind_bool_event(ds.option_pressed, "options")
    bind_bool_event(ds.share_pressed, "share")
    bind_bool_event(ds.touch_pressed, "touchpad")
    bind_bool_event(ds.microphone_pressed, "microphone")

    # Sticks
    ds.left_joystick_changed += on_left_stick
    ds.right_joystick_changed += on_right_stick

    # Motion
    ds.gyro_changed += on_gyro
    ds.accelerometer_changed += on_accel

    # Adaptive trigger analog values
    ds.l2_value_changed += on_l2
    ds.r2_value_changed += on_r2

    print("Move sticks, press buttons, tilt controller. Press PS to stop.")

    try:
        while not ds.state.ps:
            pass
    finally:
        ds.close()
