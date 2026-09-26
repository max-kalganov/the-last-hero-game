#!/usr/bin/env python3
"""
test_triggers_force.py - quick demos of DualSense L2/R2 adaptive trigger
resistance profiles using pydualsense.

    pip install pydualsense

Usage:
    python test_triggers_force.py --option 1
    python test_triggers_force.py --list
    python test_triggers_force.py --option 4 --force1 40 --force2 255 --force3 20

NOTE on resolution: pydualsense exposes 7 force "zones" per trigger
(forces[0..6]), each roughly ~14% of the full pull. There is no way to get
a true 1%-wide spike - the finest transition available is about one zone.
Option 4 approximates "75% light, then a sharp spike, then very light" by
using 5 zones for the first stretch, 1 zone for the spike, 1 zone for the
tail.
"""
import argparse
import time

from pydualsense import pydualsense, TriggerModes


def apply(trigger, mode, forces):
    """Set a trigger's mode and its 7 force zones (0-255 each)."""
    trigger.setMode(mode)
    for i, f in enumerate(forces):
        trigger.setForce(i, f)


def build_options(f1, f2, f3):
    return {
        1: (
            "Off - no resistance (baseline)",
            TriggerModes.Off,
            [0, 0, 0, 0, 0, 0, 0],
        ),
        2: (
            "Rigid - constant resistance across the whole pull",
            TriggerModes.Rigid,
            [f1, f1, f1, f1, f1, f1, f1],
        ),
        3: (
            "Pulse - vibrating resistance (buzz) across the pull",
            TriggerModes.Pulse,
            [f1, f1, f1, f1, f1, f1, f1],
        ),
        4: (
            "Custom profile - light ~75%%, brief hard spike, light tail "
            "(force1=%d, force2=%d, force3=%d)" % (f1, f2, f3),
            TriggerModes.Rigid_A,
            [f1, f1, f1, f1, f1, f2, f3],
        ),
        5: (
            "Rigid_B variant of the same profile (compare feel vs option 4)",
            TriggerModes.Rigid_B,
            [f1, f1, f1, f1, f1, f2, f3],
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="DualSense trigger resistance test")
    parser.add_argument("--option", type=int, help="which profile to run (see --list)")
    parser.add_argument("--list", action="store_true", help="list available options and exit")
    parser.add_argument("--trigger", choices=["l", "r", "both"], default="both")
    parser.add_argument("--duration", type=float, default=8.0, help="seconds to hold the effect")
    parser.add_argument("--force1", type=int, default=40, help="light baseline force (0-255)")
    parser.add_argument("--force2", type=int, default=255, help="spike force (0-255)")
    parser.add_argument("--force3", type=int, default=20, help="light tail force (0-255)")
    args = parser.parse_args()

    options = build_options(args.force1, args.force2, args.force3)

    if args.list or not args.option:
        print("Available options:")
        for k, (desc, _, _) in options.items():
            print(f"  {k}: {desc}")
        return

    if args.option not in options:
        print(f"Unknown option {args.option}. Use --list to see choices.")
        return

    desc, mode, forces = options[args.option]
    print(f"Running option {args.option}: {desc}")

    ds = pydualsense()
    ds.init()
    try:
        if args.trigger in ("l", "both"):
            apply(ds.triggerL, mode, forces)
        if args.trigger in ("r", "both"):
            apply(ds.triggerR, mode, forces)

        print(f"Effect applied. Pull the trigger now. Holding for {args.duration}s...")
        time.sleep(args.duration)
    finally:
        # release the trigger cleanly
        if args.trigger in ("l", "both"):
            ds.triggerL.setMode(TriggerModes.Off)
        if args.trigger in ("r", "both"):
            ds.triggerR.setMode(TriggerModes.Off)
        ds.close()


if __name__ == "__main__":
    main()