"""
Flow-Combat: Sword Movement Prototype (MVP)
============================================

WHAT THIS IS
    A single-file, engine-free prototype to validate the *base* sword
    movement feel before it gets split into modules / ported to a real
    engine (Panda3D, Ursina, Godot, UE, etc.):

      - a floating sword controlled by stick position + controller
        orientation (gyro),
      - a debug gamepad gizmo that mirrors the real controller in real time,
      - R2 charge/release swings, L2 guard stance, R3 recenter,
      - 3 difficulty modes that toggle how much feedback (trajectory /
        acceleration) is drawn on screen.

    Rendering is a hand-rolled perspective projector (no 3D engine
    dependency) so it runs anywhere pygame runs. Swap the render layer
    later; Gamepad / Sword / Game classes don't know how they're drawn.

CONTROLS
    Left stick   - move sword BASE in world X/Z (ground plane)
    Right stick  - move sword BASE in world Y (up/down)
    Gyro (tilt controller) - orients the BLADE (tip around base)
    R2 (hold)    - charge a strike, recording the drawn trajectory
    R2 (release) - execute the strike (power scales with charge)
    L2 (hold)    - guard stance (hilt pushes forward, blade goes defensive)
    L2 + R2 (hold together 3s) - reset the DEBUG gizmo back to its anchor
    R3           - snap sword back to the default centered position
    Cross / X    - jump (temporary, auto-returns)
    Circle / O   - crouch (temporary, auto-returns)
    1 / 2 / 3    - difficulty: Easy / Medium / Hard
    D            - toggle debug gizmo at runtime (in addition to --debug)
    ESC          - quit

RUN
    python sword_prototype.py             # normal
    python sword_prototype.py --debug     # start with the gamepad gizmo on

DEPENDENCIES
    pip install pygame
    pip install pydualsense      # optional, real DualSense gyro/triggers
    pip install spatium          # optional, your own Vec3 lib -- a
                                  # drop-in fallback is used if missing

NOTES FOR REVIEW (things I made a judgment call on -- flag if you disagree)
    - No real DualSense on hand / not connected -> falls back to a
      Keyboard+Mouse gamepad emulator so you can iterate without hardware.
      WASD = left stick, arrows = right stick, mouse move = gyro,
      LShift/RShift = L2/R2 (held, digital 0/1 not analog), Q = R3,
      Z/X = Cross/Circle, hold LShift+RShift 3s = gizmo reset.
    - "spatium" usage from your sword.py is kept as the geometric core.
      I only added a thin `SwordController` around it for motion/state --
      I did not touch your Sword class's logic.
    - Trigger "concentration" vibration: real adaptive-trigger ramping is
      attempted via pydualsense if present (see `_apply_trigger_feedback`),
      but since that can't be felt/verified without the pad, there's also
      an on-screen bar so you can validate the *curve* independent of
      hardware feel.
    - Sharp-angle stall ("Geometry Izolom") and the flow-state bonus from
      the GDD are NOT implemented here on purpose -- you asked for the base
      movement mechanic. I left clearly marked hooks
      (`# TODO(izolom)`, `# TODO(flow-bonus)`) where they plug in later,
      plus a short design note near `compute_swing_power`.
    - Jump/crouch + attack combos are stubbed (state + timers only) --
      wire real combo logic once basic movement feels right.
"""

import sys
import math
import time
import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import pygame

# --------------------------------------------------------------------------
# MODULE: geometry (Vec3) -- uses your `spatium` lib if installed, otherwise
# a minimal drop-in with the same operators your sword.py relies on.
# --------------------------------------------------------------------------
try:
    import spatium as sp
    Vec3 = sp.Vec3
except ImportError:
    class Vec3:
        __slots__ = ("x", "y", "z")

        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x, self.y, self.z = x, y, z

        def __add__(self, o):
            return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

        def __sub__(self, o):
            return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

        def __mul__(self, s):
            return Vec3(self.x * s, self.y * s, self.z * s)

        __rmul__ = __mul__

        def __or__(self, o):
            # matches sword.py's `self.base | self.tip` usage -> distance
            return self.length(o)

        def length(self, o=None):
            d = self - o if o is not None else self
            return math.sqrt(d.x * d.x + d.y * d.y + d.z * d.z)

        def normalized(self):
            l = self.length()
            if l < 1e-9:
                return Vec3(0, 0, 0)
            return Vec3(self.x / l, self.y / l, self.z / l)

        def dot(self, o):
            return self.x * o.x + self.y * o.y + self.z * o.z

        def lerp(self, o, t):
            return self + (o - self) * t

        def copy(self):
            return Vec3(self.x, self.y, self.z)


# --------------------------------------------------------------------------
# MODULE: your Sword class, unmodified (pasted in so the file stays single).
# When you split modules back out, this block == sword.py verbatim.
# --------------------------------------------------------------------------
class Sword:
    base: Vec3
    tip: Vec3
    len_to_guard_proportion: float  # len to len_to_guard_proportion from base
    __sword_len: float = None

    def __init__(self, base: Vec3, tip: Vec3, len_to_guard_proportion: float):
        self.__check_sword(base, tip, len_to_guard_proportion)
        self.base = base
        self.tip = tip
        self.len_to_guard_proportion = len_to_guard_proportion
        self._set_sword_len()

    @staticmethod
    def __check_sword(base: Vec3, tip: Vec3, len_to_guard_proportion: float):
        assert 0.05 < len_to_guard_proportion < 0.5

    def _set_sword_len(self):
        self.__sword_len = self.base | self.tip

    def get_guard_loc(self):
        base_to_tip_dir = self.tip - self.base
        return self.base + base_to_tip_dir * self.len_to_guard_proportion

    def get_sword_size(self):
        return self.__sword_len


# --------------------------------------------------------------------------
# MODULE: shared enums / constants
# --------------------------------------------------------------------------
class Difficulty(Enum):
    EASY = auto()    # trajectory + acceleration shown, time slows on charge
    MEDIUM = auto()  # trajectory shown only
    HARD = auto()    # nothing shown


SCREEN_W, SCREEN_H = 1000, 700
FPS = 60

SWORD_LENGTH = 1.0
GUARD_PROPORTION = 0.18

MOVE_SPEED = 2.2          # world units/sec at full stick deflection
STICK_DEADZONE = 0.12

MAX_CHARGE_TIME = 1.2     # seconds of R2 hold for full charge
BASE_SWING_POWER = 1.0
CHARGE_POWER_SCALE = 3.0
SWING_DURATION = 0.18     # seconds for the blade to travel its swing arc

GUARD_PUSH_FORWARD = 0.35     # how far the hilt/guard advances while in L2 stance
TRAJECTORY_SMOOTHING_ALPHA = 0.35  # EMA factor: higher = snappier, lower = smoother
TRAJECTORY_MAX_POINTS = 90

RESET_HOLD_SECONDS = 3.0  # L2+R2 held together to reset the debug gizmo

JUMP_DURATION = 0.35
CROUCH_DURATION = 0.35
JUMP_HEIGHT = 0.4
CROUCH_DROP = 0.25

AUTO_RETURN_TO_CENTER = False   # per your note: probably keep this off
AUTO_RETURN_SPEED = 1.5

GIZMO_ANCHOR_OFFSET = Vec3(0.35, 0.25, -0.6)  # gizmo position relative to sword base

COLORS = {
    "bg": (18, 18, 22),
    "grid": (40, 40, 48),
    "ref_object": (90, 130, 170),
    "sword_base": (230, 60, 60),
    "sword_tip": (60, 200, 230),
    "sword_blade": (210, 210, 220),
    "guard": (240, 200, 60),
    "trajectory": (120, 240, 140),
    "accel": (240, 120, 220),
    "gizmo": (200, 200, 60),
    "hud": (230, 230, 230),
    "hud_dim": (140, 140, 150),
}


# --------------------------------------------------------------------------
# MODULE: gamepad abstraction
#   GamepadState -- plain data snapshot for one frame
#   GamepadBackend -- interface
#   DualSenseBackend -- real hardware via pydualsense (optional dep)
#   KeyboardMouseBackend -- fallback so you can iterate without the pad
#   Gamepad -- wraps a backend, adds derived state (hold timers, gizmo pose)
# --------------------------------------------------------------------------
@dataclass
class GamepadState:
    left_stick: tuple = (0.0, 0.0)      # (x, y) each in [-1, 1]
    right_stick: tuple = (0.0, 0.0)
    l2: float = 0.0                      # analog trigger [0, 1]
    r2: float = 0.0
    l1: bool = False
    r1: bool = False
    r3: bool = False
    cross: bool = False
    circle: bool = False
    gyro: tuple = (0.0, 0.0, 0.0)         # pitch, yaw, roll rate (deg/s-ish)
    accel: tuple = (0.0, 0.0, 0.0)        # raw accelerometer, arbitrary units
    connected: bool = False


class GamepadBackend:
    """Interface every backend implements."""

    def poll(self) -> GamepadState:
        raise NotImplementedError

    def set_trigger_feedback(self, level: float):
        """level in [0,1] -- approximate 'concentration' resistance on R2."""
        pass

    def close(self):
        pass


class DualSenseBackend(GamepadBackend):
    """Real hardware via `pydualsense`. Only constructed if the lib AND a
    physical controller are both available; otherwise Gamepad() falls back.
    """

    def __init__(self):
        from pydualsense import pydualsense  # may raise ImportError
        self._ds = pydualsense()
        self._ds.init()  # may raise if no device connected

    def poll(self) -> GamepadState:
        s = self._ds.state
        return GamepadState(
            left_stick=(self._axis(s.LX), self._axis(s.LY)),
            right_stick=(self._axis(s.RX), self._axis(s.RY)),
            l2=s.L2 / 255.0,
            r2=s.R2 / 255.0,
            l1=bool(s.L1),
            r1=bool(s.R1),
            r3=bool(s.R3),
            cross=bool(s.cross),
            circle=bool(s.circle),
            gyro=(s.gyro.X, s.gyro.Y, s.gyro.Z),
            accel=(s.accelerometer.X, s.accelerometer.Y, s.accelerometer.Z),
            connected=True,
        )

    @staticmethod
    def _axis(v):
        # pydualsense sticks are 0..255; recenter + normalize to [-1, 1]
        return max(-1.0, min(1.0, (v - 128) / 127.0))

    def set_trigger_feedback(self, level: float):
        # NOTE: exact adaptive-trigger call depends on your pydualsense
        # version's API (setTriggerEffect / setRigidMode, etc). Wrapped in
        # try/except so a version mismatch never crashes the prototype --
        # replace with the correct call for the version you pin.
        try:
            from pydualsense import TriggerModes
            force = int(level * 255)
            self._ds.triggerR.setMode(TriggerModes.Rigid)
            self._ds.triggerR.setForce(1, force)
        except Exception:
            pass

    def close(self):
        try:
            self._ds.close()
        except Exception:
            pass


class KeyboardMouseBackend(GamepadBackend):
    """Fallback control scheme so the prototype is playable without a
    DualSense connected. Mouse delta stands in for gyro, WASD for the left
    stick, arrow keys for the right stick, shift keys for L2/R2 (digital).
    """

    def __init__(self):
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)
        self._last_mouse = pygame.mouse.get_pos()

    def poll(self) -> GamepadState:
        keys = pygame.key.get_pressed()
        lx = (keys[pygame.K_d] - keys[pygame.K_a])
        ly = (keys[pygame.K_w] - keys[pygame.K_s])
        rx = (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT])
        ry = (keys[pygame.K_UP] - keys[pygame.K_DOWN])

        mx, my = pygame.mouse.get_pos()
        dx, dy = mx - self._last_mouse[0], my - self._last_mouse[1]
        pygame.mouse.set_pos((SCREEN_W // 2, SCREEN_H // 2))
        self._last_mouse = (SCREEN_W // 2, SCREEN_H // 2)

        return GamepadState(
            left_stick=(float(lx), float(ly)),
            right_stick=(float(rx), float(ry)),
            l2=1.0 if keys[pygame.K_LSHIFT] else 0.0,
            r2=1.0 if keys[pygame.K_RSHIFT] else 0.0,
            l1=keys[pygame.K_q],
            r1=keys[pygame.K_e],
            r3=keys[pygame.K_r],
            cross=keys[pygame.K_z],
            circle=keys[pygame.K_x],
            gyro=(dy * 2.0, dx * 2.0, 0.0),
            accel=(dx * 0.1, dy * 0.1, 0.0),
            connected=False,
        )

    def close(self):
        pygame.event.set_grab(False)
        pygame.mouse.set_visible(True)


class Gamepad:
    """Wraps whichever backend is available and adds derived, backend-agnostic
    state: the L2+R2 hold timer, integrated gyro orientation for the debug
    gizmo, and a "just reset" edge event.
    """

    def __init__(self):
        self.backend, self.using_hardware = self._pick_backend()
        self.state = GamepadState()
        self._l2_r2_hold_start = None
        self.just_reset = False

        # Integrated orientation (pitch, yaw) purely from gyro rate, used to
        # orient both the sword blade and the debug gizmo. This is a naive
        # integration (no drift correction) -- fine for a movement prototype.
        self.orientation_pitch = 0.0
        self.orientation_yaw = 0.0
        self.gizmo_offset = GIZMO_ANCHOR_OFFSET.copy()

    @staticmethod
    def _pick_backend():
        try:
            return DualSenseBackend(), True
        except Exception:
            print("[gamepad] DualSense not available -> using Keyboard+Mouse fallback.")
            return KeyboardMouseBackend(), False

    def update(self, dt: float):
        self.state = self.backend.poll()
        self.just_reset = False

        # Integrate gyro into an orientation usable for aiming the blade.
        gyro_pitch, gyro_yaw, _ = self.state.gyro
        self.orientation_pitch += gyro_pitch * dt * 0.02
        self.orientation_yaw += gyro_yaw * dt * 0.02
        self.orientation_pitch = max(-1.4, min(1.4, self.orientation_pitch))

        # L2 + R2 held together for RESET_HOLD_SECONDS -> reset gizmo anchor.
        both_held = self.state.l2 > 0.5 and self.state.r2 > 0.5
        if both_held:
            if self._l2_r2_hold_start is None:
                self._l2_r2_hold_start = time.time()
            elif time.time() - self._l2_r2_hold_start >= RESET_HOLD_SECONDS:
                self.gizmo_offset = GIZMO_ANCHOR_OFFSET.copy()
                self.just_reset = True
                self._l2_r2_hold_start = None  # don't refire every frame
        else:
            self._l2_r2_hold_start = None

    def reset_hold_progress(self) -> float:
        """0..1 progress toward the 3s reset hold, for an on-screen indicator."""
        if self._l2_r2_hold_start is None:
            return 0.0
        return min(1.0, (time.time() - self._l2_r2_hold_start) / RESET_HOLD_SECONDS)

    def apply_trigger_feedback(self, level: float):
        self.backend.set_trigger_feedback(level)

    def get_gizmo_pose(self, anchor: Vec3):
        """Debug gizmo position/orientation. It's fixed at an offset behind
        the sword (anchor-relative, NOT world-relative) so it never drifts
        just because the player's laptop/camera doesn't move -- only the
        controller's own rotation should visibly change it.
        """
        pos = anchor + self.gizmo_offset
        return pos, self.orientation_pitch, self.orientation_yaw

    def close(self):
        self.backend.close()


# --------------------------------------------------------------------------
# MODULE: sword controller -- owns a `Sword` and drives it from input.
# --------------------------------------------------------------------------
class SwingState(Enum):
    IDLE = auto()
    CHARGING = auto()
    SWINGING = auto()
    GUARD = auto()


class SwordController:
    def __init__(self):
        base = Vec3(0.0, 1.0, 0.0)
        tip = Vec3(0.0, 1.0, SWORD_LENGTH)
        self.sword = Sword(base, tip, GUARD_PROPORTION)
        self.default_base = base.copy()

        self.state = SwingState.IDLE
        self.charge_start = None
        self.charge = 0.0                      # 0..1
        self.velocity = Vec3(0, 0, 0)
        self.prev_tip = tip.copy()
        self.acceleration = Vec3(0, 0, 0)
        self._prev_velocity = Vec3(0, 0, 0)

        self.trajectory = deque(maxlen=TRAJECTORY_MAX_POINTS)   # smoothed tip points while charging
        self._smoothed_dir = Vec3(0, 0, 1)

        self.jump_t = None
        self.crouch_t = None
        self.vertical_offset = 0.0

        self.swing_t = 0.0
        self.swing_start_tip = tip.copy()
        self.swing_target_tip = tip.copy()
        self.swing_power = 0.0

    # -- input handling -----------------------------------------------
    def update(self, dt: float, pad: Gamepad):
        s = pad.state
        self._handle_movement(dt, s)
        self._handle_orientation(dt, pad)
        self._handle_jump_crouch(dt, s)
        self._handle_guard_and_swing(dt, s, pad)
        self._update_kinematics(dt)

    def _dz(self, v):
        return 0.0 if abs(v) < STICK_DEADZONE else v

    def _handle_movement(self, dt, s: GamepadState):
        lx, ly = self._dz(s.left_stick[0]), self._dz(s.left_stick[1])
        rx, ry = self._dz(s.right_stick[0]), self._dz(s.right_stick[1])

        move = Vec3(lx, ry, ly) * (MOVE_SPEED * dt)
        # While actively swinging we don't let the stick fight the swing arc.
        if self.state != SwingState.SWINGING:
            self.sword.base = self.sword.base + move
            self.sword.tip = self.sword.tip + move

        if s.r3:
            # Snap back to the default centered position instantly.
            delta = self.default_base - self.sword.base
            self.sword.base = self.sword.base + delta
            self.sword.tip = self.sword.tip + delta

        if AUTO_RETURN_TO_CENTER and self.state == SwingState.IDLE:
            # Disabled by default per your note -- left here in case you
            # want to re-enable a slow drift back to center later.
            delta = self.default_base - self.sword.base
            step = delta * min(1.0, AUTO_RETURN_SPEED * dt)
            self.sword.base = self.sword.base + step
            self.sword.tip = self.sword.tip + step

    def _handle_orientation(self, dt, pad: Gamepad):
        if self.state == SwingState.SWINGING:
            return  # orientation is driven by the swing arc instead
        pitch, yaw = pad.orientation_pitch, pad.orientation_yaw
        direction = Vec3(math.sin(yaw), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
        self.sword.tip = self.sword.base + direction.normalized() * SWORD_LENGTH

    def _handle_jump_crouch(self, dt, s: GamepadState):
        now = time.time()
        if s.cross and self.jump_t is None and self.crouch_t is None:
            self.jump_t = now
            # TODO(combo): a strike thrown during self.jump_t window should
            # get an "aerial" tag here so damage/animation can branch on it.
        if s.circle and self.crouch_t is None and self.jump_t is None:
            self.crouch_t = now
            # TODO(combo): a strike thrown during self.crouch_t window should
            # get a "low" tag here (e.g. bonus vs a raised guard).

        if self.jump_t is not None:
            t = (now - self.jump_t) / JUMP_DURATION
            if t >= 1.0:
                self.jump_t = None
                self.vertical_offset = 0.0
            else:
                self.vertical_offset = math.sin(t * math.pi) * JUMP_HEIGHT
        elif self.crouch_t is not None:
            t = (now - self.crouch_t) / CROUCH_DURATION
            if t >= 1.0:
                self.crouch_t = None
                self.vertical_offset = 0.0
            else:
                self.vertical_offset = -math.sin(t * math.pi) * CROUCH_DROP
        else:
            self.vertical_offset = 0.0

    def _handle_guard_and_swing(self, dt, s: GamepadState, pad: Gamepad):
        # --- Guard stance (L2) ---
        if s.l2 > 0.5 and self.state in (SwingState.IDLE, SwingState.GUARD):
            self.state = SwingState.GUARD
        elif self.state == SwingState.GUARD and s.l2 <= 0.5:
            self.state = SwingState.IDLE

        # --- Charge / release (R2) ---
        if s.r2 > 0.5 and self.state in (SwingState.IDLE, SwingState.GUARD, SwingState.CHARGING):
            if self.state != SwingState.CHARGING:
                self.charge_start = time.time()
                self.trajectory.clear()
            self.state = SwingState.CHARGING
            self.charge = min(1.0, (time.time() - self.charge_start) / MAX_CHARGE_TIME)
            self._smoothed_dir = self._smoothed_dir.lerp(
                (self.sword.tip - self.sword.base).normalized(), TRAJECTORY_SMOOTHING_ALPHA
            )
            self.trajectory.append(self.sword.tip.copy())
            pad.apply_trigger_feedback(self.charge)  # rising R2 resistance = "concentration"

        elif self.state == SwingState.CHARGING and s.r2 <= 0.5:
            self._start_swing()
            pad.apply_trigger_feedback(0.0)

        # --- Swing playback ---
        if self.state == SwingState.SWINGING:
            self.swing_t += dt / SWING_DURATION
            t = min(1.0, self.swing_t)
            eased = 1.0 - (1.0 - t) ** 3  # ease-out cubic: fast start, soft stop
            self.sword.tip = self.swing_start_tip.lerp(self.swing_target_tip, eased)
            if t >= 1.0:
                self.state = SwingState.IDLE
                self.charge = 0.0

    def _start_swing(self):
        """DESIGN NOTE (acceleration mechanic):
        Swing power currently comes from two inputs:
          1. charge (hold duration, 0..1) -- how "wound up" the strike is.
          2. draw speed -- how fast the tip was moving at the moment of
             release (captured from `self.velocity`, itself smoothed).
        power = BASE + charge * CHARGE_SCALE + release_speed * SPEED_SCALE
        This rewards both "load it up" (tank charge) and "whip it fast"
        (skill-based motion) rather than just holding the trigger. Tune the
        two scale constants against playtest feel.
        TODO(izolom): once implemented, a sharp direction change vs. the
        previous swing's exit vector should zero this out entirely (stall).
        TODO(flow-bonus): a release direction aligned with current
        blade-side momentum should multiply this up.
        """
        release_speed = self.velocity.length()
        self.swing_power = (
            BASE_SWING_POWER
            + self.charge * CHARGE_POWER_SCALE
            + release_speed * 0.5
        )
        self.state = SwingState.SWINGING
        self.swing_t = 0.0
        self.swing_start_tip = self.sword.tip.copy()
        self.swing_target_tip = self.sword.base + self._smoothed_dir.normalized() * (
            SWORD_LENGTH * (1.0 + 0.3 * self.charge)
        )

    def _update_kinematics(self, dt):
        if dt <= 0:
            return
        new_velocity = (self.sword.tip - self.prev_tip) * (1.0 / dt)
        self.acceleration = (new_velocity - self._prev_velocity) * (1.0 / dt)
        self._prev_velocity = self.velocity
        self.velocity = new_velocity
        self.prev_tip = self.sword.tip.copy()

    def get_guard_forward_offset(self, s: GamepadState) -> Vec3:
        """While in GUARD, push the hilt forward along the blade axis."""
        if self.state != SwingState.GUARD:
            return Vec3(0, 0, 0)
        forward = (self.sword.tip - self.sword.base).normalized()
        return forward * GUARD_PUSH_FORWARD


# --------------------------------------------------------------------------
# MODULE: world + camera + a hand-rolled perspective projector
# --------------------------------------------------------------------------
class RefObject:
    def __init__(self, center: Vec3, size: float, kind: str):
        self.center = center
        self.size = size
        self.kind = kind  # "cube" or "pyramid" -- purely visual reference

    def edges_world(self):
        c, s = self.center, self.size
        if self.kind == "cube":
            verts = [
                c + Vec3(dx, dy, dz)
                for dx in (-s, s) for dy in (-s, s) for dz in (-s, s)
            ]
            idx_edges = [
                (0, 1), (0, 2), (0, 4), (3, 1), (3, 2), (3, 7),
                (5, 1), (5, 4), (5, 7), (6, 2), (6, 4), (6, 7),
            ]
            return [(verts[a], verts[b]) for a, b in idx_edges]
        else:  # pyramid
            apex = c + Vec3(0, s, 0)
            base_pts = [
                c + Vec3(s, -s, s), c + Vec3(s, -s, -s),
                c + Vec3(-s, -s, -s), c + Vec3(-s, -s, s),
            ]
            edges = [(base_pts[i], base_pts[(i + 1) % 4]) for i in range(4)]
            edges += [(apex, bp) for bp in base_pts]
            return edges


class Camera:
    """Simple third-person follow camera + perspective projection.
    No matrix library needed -- explicit camera-space transform below.
    """

    def __init__(self):
        self.pos = Vec3(0.0, 1.6, -3.0)
        self.target = Vec3(0.0, 1.0, 0.0)
        self.fov = 70.0
        self.follow_lerp = 4.0

    def update(self, dt, focus: Vec3):
        desired_pos = focus + Vec3(0.0, 0.55, -2.6)
        t = min(1.0, self.follow_lerp * dt)
        self.pos = self.pos.lerp(desired_pos, t)
        self.target = self.target.lerp(focus, t)

    def project(self, p: Vec3):
        """Returns (screen_x, screen_y, depth) or None if behind the camera."""
        # Camera-space basis: forward = target-pos, simple world-up.
        forward = (self.target - self.pos).normalized()
        world_up = Vec3(0, 1, 0)
        right = Vec3(
            forward.y * world_up.z - forward.z * world_up.y,
            forward.z * world_up.x - forward.x * world_up.z,
            forward.x * world_up.y - forward.y * world_up.x,
        ).normalized()
        up = Vec3(
            right.y * forward.z - right.z * forward.y,
            right.z * forward.x - right.x * forward.z,
            right.x * forward.y - right.y * forward.x,
        )

        rel = p - self.pos
        cx = rel.dot(right)
        cy = rel.dot(up)
        cz = rel.dot(forward)

        if cz <= 0.05:
            return None  # behind / too close to camera

        f = 1.0 / math.tan(math.radians(self.fov) / 2.0)
        sx = (cx * f / cz) * (SCREEN_H / 2) + SCREEN_W / 2
        sy = -(cy * f / cz) * (SCREEN_H / 2) + SCREEN_H / 2
        return sx, sy, cz


# --------------------------------------------------------------------------
# MODULE: rendering helpers (pygame primitives on top of Camera.project)
# --------------------------------------------------------------------------
def draw_line3d(surface, cam: Camera, a: Vec3, b: Vec3, color, width=2):
    pa, pb = cam.project(a), cam.project(b)
    if pa and pb:
        pygame.draw.line(surface, color, (pa[0], pa[1]), (pb[0], pb[1]), width)


def draw_point3d(surface, cam: Camera, p: Vec3, color, radius=6):
    pp = cam.project(p)
    if pp:
        pygame.draw.circle(surface, color, (int(pp[0]), int(pp[1])), radius)


def draw_ground_grid(surface, cam: Camera, size=10, step=1):
    for i in range(-size, size + 1, step):
        draw_line3d(surface, cam, Vec3(i, 0, -size), Vec3(i, 0, size), COLORS["grid"], 1)
        draw_line3d(surface, cam, Vec3(-size, 0, i), Vec3(size, 0, i), COLORS["grid"], 1)


def draw_ref_objects(surface, cam: Camera, objects):
    for obj in objects:
        for a, b in obj.edges_world():
            draw_line3d(surface, cam, a, b, COLORS["ref_object"], 2)


def draw_sword(surface, cam: Camera, sword: Sword, vertical_offset: float, guard_push: Vec3):
    base = sword.base + Vec3(0, vertical_offset, 0) + guard_push
    tip = sword.tip + Vec3(0, vertical_offset, 0)
    guard_center = base + (tip - base) * sword.len_to_guard_proportion

    draw_line3d(surface, cam, base, tip, COLORS["sword_blade"], 4)
    draw_point3d(surface, cam, base, COLORS["sword_base"], 8)
    draw_point3d(surface, cam, tip, COLORS["sword_tip"], 6)

    # Perpendicular guard indicator: a short stick through guard_center,
    # perpendicular to the blade axis, drawn in the camera's local "right"
    # direction so it always reads as crossing the blade on screen.
    axis = (tip - base).normalized()
    arbitrary = Vec3(0, 1, 0) if abs(axis.y) < 0.9 else Vec3(1, 0, 0)
    guard_dir = Vec3(
        axis.y * arbitrary.z - axis.z * arbitrary.y,
        axis.z * arbitrary.x - axis.x * arbitrary.z,
        axis.x * arbitrary.y - axis.y * arbitrary.x,
    ).normalized()
    half = 0.12
    draw_line3d(
        surface, cam,
        guard_center - guard_dir * half,
        guard_center + guard_dir * half,
        COLORS["guard"], 4,
    )


def draw_trajectory(surface, cam: Camera, points, difficulty: Difficulty):
    if difficulty == Difficulty.HARD or len(points) < 2:
        return
    pts = list(points)
    for i in range(1, len(pts)):
        fade = i / len(pts)
        color = tuple(int(c * fade) for c in COLORS["trajectory"])
        draw_line3d(surface, cam, pts[i - 1], pts[i], color, 2)


def draw_acceleration(surface, cam: Camera, tip: Vec3, accel: Vec3, difficulty: Difficulty):
    if difficulty != Difficulty.EASY:
        return
    # Scaled down for legibility -- raw accel magnitude can be large/noisy.
    end = tip + accel * 0.05
    draw_line3d(surface, cam, tip, end, COLORS["accel"], 3)


def draw_gizmo(surface, cam: Camera, pos: Vec3, pitch: float, yaw: float):
    """Stand-in for a 3D controller model: a small oriented cross/arrow.
    (No offline 3D asset library available here -- swap this for an actual
    controller mesh once you're in a real engine / have a model on disk.)
    """
    forward = Vec3(math.sin(yaw), math.sin(pitch), math.cos(yaw) * math.cos(pitch)).normalized()
    up = Vec3(0, 1, 0)
    right = Vec3(
        forward.y * up.z - forward.z * up.y,
        forward.z * up.x - forward.x * up.z,
        forward.x * up.y - forward.y * up.x,
    ).normalized()

    size = 0.12
    tip = pos + forward * (size * 1.6)
    left_wing = pos - forward * size * 0.3 + right * size
    right_wing = pos - forward * size * 0.3 - right * size

    draw_line3d(surface, cam, pos, tip, COLORS["gizmo"], 2)
    draw_line3d(surface, cam, tip, left_wing, COLORS["gizmo"], 2)
    draw_line3d(surface, cam, tip, right_wing, COLORS["gizmo"], 2)
    draw_point3d(surface, cam, pos, COLORS["gizmo"], 4)


def draw_hud(surface, font, ctl: SwordController, pad: Gamepad, difficulty: Difficulty, debug_on: bool):
    lines = [
        f"Difficulty: {difficulty.name}   (1/2/3 to switch)   Debug gizmo: {'ON' if debug_on else 'off'} (D)",
        f"Backend: {'DualSense' if pad.using_hardware else 'Keyboard+Mouse fallback'}",
        f"State: {ctl.state.name}   Charge: {ctl.charge:.2f}   Swing power (last): {ctl.swing_power:.2f}",
    ]
    y = 10
    for line in lines:
        surf = font.render(line, True, COLORS["hud"])
        surface.blit(surf, (10, y))
        y += 20

    # Charge / "concentration" bar (mirrors what we try to send to the
    # adaptive trigger, so you can validate the curve without hardware).
    bar_w, bar_h = 220, 14
    pygame.draw.rect(surface, COLORS["hud_dim"], (10, y + 4, bar_w, bar_h), 1)
    pygame.draw.rect(surface, COLORS["accel"], (10, y + 4, int(bar_w * ctl.charge), bar_h))

    # Reset-hold progress (L2+R2 held together).
    reset_progress = pad.reset_hold_progress()
    if reset_progress > 0:
        y2 = y + 26
        pygame.draw.rect(surface, COLORS["hud_dim"], (10, y2, bar_w, bar_h), 1)
        pygame.draw.rect(surface, COLORS["gizmo"], (10, y2, int(bar_w * reset_progress), bar_h))
        surf = font.render("Resetting gizmo (hold L2+R2)...", True, COLORS["hud_dim"])
        surface.blit(surf, (10 + bar_w + 10, y2 - 1))


# --------------------------------------------------------------------------
# MODULE: main game loop
# --------------------------------------------------------------------------
class Game:
    def __init__(self, debug_start: bool):
        pygame.init()
        pygame.display.set_caption("Flow-Combat -- Movement Prototype")
        self.surface = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)

        self.pad = Gamepad()
        self.controller = SwordController()
        self.camera = Camera()
        self.difficulty = Difficulty.MEDIUM
        self.debug_on = debug_start

        random.seed(0)
        self.ref_objects = [
            RefObject(Vec3(3, 1, 4), 0.6, "cube"),
            RefObject(Vec3(-3, 0.6, 5), 0.6, "pyramid"),
            RefObject(Vec3(0, 0.5, 8), 0.8, "cube"),
            RefObject(Vec3(-4, 0.5, -2), 0.5, "pyramid"),
        ]

        self.running = True

    def run(self):
        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                dt = self._apply_slowmo(dt)
                self._handle_events()
                self.pad.update(dt)
                self.controller.update(dt, self.pad)
                self.camera.update(dt, self.controller.sword.base)
                self._render()
        finally:
            self.pad.close()
            pygame.quit()

    def _apply_slowmo(self, dt):
        # EASY mode slows time while charging, so fast, precise reads of the
        # trajectory/acceleration overlay are actually readable.
        if self.difficulty == Difficulty.EASY and self.controller.state == SwingState.CHARGING:
            return dt * 0.35
        return dt

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_1:
                    self.difficulty = Difficulty.EASY
                elif event.key == pygame.K_2:
                    self.difficulty = Difficulty.MEDIUM
                elif event.key == pygame.K_3:
                    self.difficulty = Difficulty.HARD
                elif event.key == pygame.K_d:
                    self.debug_on = not self.debug_on

    def _render(self):
        self.surface.fill(COLORS["bg"])
        draw_ground_grid(self.surface, self.camera)
        draw_ref_objects(self.surface, self.camera, self.ref_objects)

        ctl = self.controller
        guard_push = ctl.get_guard_forward_offset(self.pad.state)
        draw_sword(self.surface, self.camera, ctl.sword, ctl.vertical_offset, guard_push)
        draw_trajectory(self.surface, self.camera, ctl.trajectory, self.difficulty)
        draw_acceleration(self.surface, self.camera, ctl.sword.tip, ctl.acceleration, self.difficulty)

        if self.debug_on:
            pos, pitch, yaw = self.pad.get_gizmo_pose(ctl.sword.base)
            draw_gizmo(self.surface, self.camera, pos, pitch, yaw)

        draw_hud(self.surface, self.font, ctl, self.pad, self.difficulty, self.debug_on)
        pygame.display.flip()


def main():
    debug_start = "--debug" in sys.argv
    Game(debug_start).run()


if __name__ == "__main__":
    main()
