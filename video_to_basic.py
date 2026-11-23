#!/usr/bin/env python3
"""Convert video to a numbered GMBASIC graphics program."""

import argparse
from fractions import Fraction
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
RUNS = re.compile(rb"\x00+|\x01+")


def merged_rectangles(frame, width):
    """Merge matching runs in neighboring rows into filled rectangles."""
    rectangles = ([], [])
    active = {}
    for y, offset in enumerate(range(0, len(frame), width)):
        current = {}
        for run in RUNS.finditer(frame, offset, offset + width):
            start, end = run.span()
            key = (frame[start], start - offset, end - offset)
            current[key] = active.pop(key, y)
        for (color, x1, x2), top in active.items():
            rectangles[color].append((x1, top, x2, y))
        active = current

    bottom = len(frame) // width
    for (color, x1, x2), top in active.items():
        rectangles[color].append((x1, top, x2, bottom))
    return rectangles


def frame_commands(frame, width, height):
    black, white = merged_rectangles(frame, width)
    transposed = b"".join(frame[x::width] for x in range(width))
    columns = merged_rectangles(transposed, height)
    black = min(black, [(y1, x1, y2, x2) for x1, y1, x2, y2 in columns[0]], key=len)
    white = min(white, [(y1, x1, y2, x2) for x1, y1, x2, y2 in columns[1]], key=len)

    white_background = 2 + len(black) + bool(black)
    black_background = len(white) + bool(white)
    commands = []
    if white_background < black_background:
        commands.extend(("SETDRAWCOLOR(WHITE)", f"FRECT(0,0,{CANVAS_WIDTH},{CANVAS_HEIGHT})"))
        shapes, color = black, "BLACK"
    else:
        shapes, color = white, "WHITE"

    if shapes:
        commands.append(f"SETDRAWCOLOR({color})")
        for x1, y1, x2, y2 in shapes:
            commands.append(
                f"FRECT({x1 * CANVAS_WIDTH // width},{y1 * CANVAS_HEIGHT // height},"
                f"{x2 * CANVAS_WIDTH // width},{y2 * CANVAS_HEIGHT // height})"
            )
    return commands


def polygon_commands(frame, width, height):
    """Use marching squares to give the thresholded silhouette diagonal edges."""
    # Repeat edge samples at the canvas boundary so silhouettes meet the border.
    rows = [frame[y:y + width] for y in range(0, len(frame), width)]
    rows = [row[:1] + row + row[-1:] for row in [rows[0], *rows, rows[-1]]]
    xs = polygon_axis(width, CANVAS_WIDTH)
    ys = polygon_axis(height, CANVAS_HEIGHT)
    stride = 2 * (width + 1)
    solid = bytearray(stride * 2 * (height + 1))
    commands = []

    for y, (top, bottom) in enumerate(zip(rows, rows[1:])):
        for x in range(width + 1):
            mask = (top[x], top[x + 1], bottom[x + 1], bottom[x])
            count = sum(mask)
            if not count:
                continue
            col, row = 2 * x, 2 * y
            offset = row * stride + col
            diagonal = mask in ((1, 0, 1, 0), (0, 1, 0, 1))

            # Each cell has four quarters. Merge solid quarters across cells.
            if count >= 2 and not diagonal:
                solid[offset] = mask[0]
                solid[offset + 1] = mask[1]
                solid[offset + stride + 1] = mask[2]
                solid[offset + stride] = mask[3]
            if count == 4 or (count == 2 and not diagonal):
                continue

            left, mx, right = xs[col:col + 3]
            upper, my, lower = ys[row:row + 3]
            edges = ((mx, upper), (right, my), (mx, lower), (left, my))
            if count == 3:
                gap = mask.index(0)
                triangles = [(edges[gap - 1], edges[gap], (mx, my))]
            else:
                corners = ((left, upper), (right, upper), (right, lower), (left, lower))
                # Diagonally touching samples each get their own triangle.
                triangles = [(corners[i], edges[i], edges[i - 1]) for i in range(4) if mask[i]]
            for triangle in triangles:
                coords = ",".join(f"{value:.3f}" for point in triangle for value in point)
                commands.append(f"FTRI({coords})")

    for x1, y1, x2, y2 in merged_rectangles(solid, stride)[1]:
        commands.append(f"FRECT({xs[x1]:.3f},{ys[y1]:.3f},{xs[x2]:.3f},{ys[y2]:.3f})")
    return ["SETDRAWCOLOR(WHITE)", *commands] if commands else []


def polygon_axis(size, extent):
    samples = [0, *((i + 0.5) * extent / size for i in range(size)), extent]
    coordinates = [samples[0]]
    for left, right in zip(samples, samples[1:]):
        coordinates.extend(((left + right) / 2, right))
    return coordinates


def write_basic(source, output, width, height, threshold, render_frame=frame_commands):
    threshold_table = bytes(int(value >= threshold) for value in range(256))
    previous = None
    frames = 0
    line = 10
    frame_size = width * height

    while raw := source.read(frame_size):
        if len(raw) != frame_size:
            raise ValueError("FFmpeg returned an incomplete decoded frame")
        statements = []
        if frames == 0:
            # The first CLS starts a frame. Later ones publish it.
            statements.append("CLS")
        frame = raw.translate(threshold_table)
        if frame != previous:
            statements.extend(render_frame(frame, width, height))
            statements.append("CLS")
            previous = frame
        statements.append("VSYNC")

        frames += 1
        for statement in statements:
            output.write(f"{line} {statement}\n")
            line += 10

    output.write(f"{line} END\n")
    return frames


def decoder_command(args):
    aspect = f"(dar*{args.width}*{CANVAS_HEIGHT}/({args.height}*{CANVAS_WIDTH}))"
    filters = (
        f"fps={args.fps},"
        f"scale=w='max(1,round(min({args.width},{args.height}*{aspect})))':"
        f"h='max(1,round(min({args.height},{args.width}/{aspect})))':flags={args.resample},"
        f"setsar=1,format=rgb24,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2:black,"
        "format=gray"
    )
    command = [args.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-v", "error", "-xerror"]
    if args.start:
        command.extend(("-ss", f"{args.start:.9f}"))
    command.extend(("-i", str(args.input.absolute()), "-map", "0:v:0", "-an", "-sn", "-dn"))
    if args.duration is not None:
        command.extend(("-t", f"{args.duration:.9f}"))
    command.extend(("-vf", filters, "-fps_mode", "passthrough", "-c:v", "rawvideo",
                    "-threads:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"))
    return command


def convert(args):
    if not args.input.is_file():
        raise ValueError(f"Input is not a file: {args.input}")
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Input and output paths must be different")

    temporary = None
    try:
        with tempfile.TemporaryFile() as log, tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", newline="\n", prefix=".video-to-basic-",
            suffix=".tmp", dir=args.output.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            with subprocess.Popen(decoder_command(args), stdout=subprocess.PIPE, stderr=log) as process:
                try:
                    render_frame = polygon_commands if args.render == "polygons" else frame_commands
                    frames = write_basic(process.stdout, output, args.width, args.height, args.threshold, render_frame)
                except BaseException:
                    if process.poll() is None:
                        process.kill()
                    raise
                status = process.wait()
            if status:
                end = log.seek(0, os.SEEK_END)
                log.seek(max(0, end - 4096))
                details = log.read().decode(errors="replace").strip()
                raise ValueError(f"FFmpeg exited with status {status}\n{details}")
        if not frames:
            raise ValueError("FFmpeg decoded no frames in the selected range")
        temporary.replace(args.output)
        return frames
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def positive_fps(value):
    try:
        fps = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise argparse.ArgumentTypeError("FPS must be a positive number or fraction") from error
    if fps <= 0:
        raise argparse.ArgumentTypeError("FPS must be positive")
    return fps


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input video file")
    parser.add_argument("output", type=Path, help="destination .bas file")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable or path")
    parser.add_argument("--fps", type=positive_fps, default=Fraction(60), help="output frames per second")
    parser.add_argument("--width", type=int, default=80, help="sampling width")
    parser.add_argument("--height", type=int, default=60, help="sampling height")
    parser.add_argument("--threshold", type=int, default=128, help="black-white cutoff (0–255)")
    parser.add_argument("--resample", choices=("area", "bicubic", "lanczos"), default="area",
                        help="resize filter before thresholding (default: area)")
    parser.add_argument("--render", choices=("rects", "polygons"), default="rects",
                        help="use rectangles or smoother polygon edges (default: rects)")
    parser.add_argument("--start", type=float, default=0, help="excerpt start in seconds")
    parser.add_argument("--duration", type=float, help="excerpt length in seconds")
    args = parser.parse_args(argv)
    if not (1 <= args.width <= CANVAS_WIDTH and 1 <= args.height <= CANVAS_HEIGHT):
        parser.error(f"resolution must fit within {CANVAS_WIDTH}x{CANVAS_HEIGHT}")
    if not 0 <= args.threshold <= 255:
        parser.error("--threshold must be between 0 and 255")
    if not math.isfinite(args.start) or args.start < 0:
        parser.error("--start must be a finite nonnegative number")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("--duration must be a finite positive number")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        frames = convert(args)
        print(f"Wrote {frames} frames to {args.output} (sampled at {args.fps} FPS)")
    except (OSError, ValueError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
