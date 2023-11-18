#!/usr/bin/env python3

import subprocess
import threading
import os
import sys
import platform
import queue


BYTES_IN_MB = 1024*1024
output_queue = queue.Queue()


def make_dirs(directory):
    try:
        os.makedirs(directory)
    except PermissionError:
        print("Permission denied: Could not create destination directory.")
        sys.exit(1)
    except OSError as e:
        print(
            f"An error occurred while creating the destination directory: {e}"
            )
        sys.exit(1)


def progress_bar(copied, total, bar_length=50):
    progress = float(copied) / float(total)
    arrow = '=' * int(round(progress * bar_length))
    spaces = ' ' * (bar_length - len(arrow))

    return f"[{arrow}{spaces}]"


def update_size_stats(source, target_path, du_flag):
    remaining_size = 1
    copied_size = 0
    total_size = int(
                subprocess.check_output(['du', du_flag, source]).split()[0]
                )
    if os.path.exists(target_path):
        copied_size = int(subprocess.check_output(
            ['du', du_flag, target_path]).split()[0]
            )
        if platform.system() == 'Darwin':
            total_size *= 1024
            copied_size *= 1024

    remaining_size = total_size - copied_size
    output_queue.put(
        f"Total size: {round(total_size / BYTES_IN_MB, 2)} MB | Copied: {round(copied_size / BYTES_IN_MB, 2)} MB | Remaining: {round(remaining_size / BYTES_IN_MB, 2)} MB"
        )
    progress_str = progress_bar(copied_size, total_size)
    output_queue.put(progress_str)


def get_params(source, dest_dir):
    du_flag = '-sb' if platform.system() == 'Linux' else '-sk'
    if os.path.isfile(source):
        target_path = os.path.join(dest_dir, os.path.basename(source))
    else:
        target_path = dest_dir
    
    return du_flag, target_path


def calculate_stats(source, dest_dir):
    if not os.path.exists(dest_dir):
        make_dirs(dest_dir)

    du_flag, target_path = get_params(source, dest_dir)

    while True:
        try:
            update_size_stats(source, target_path, du_flag)

        except subprocess.CalledProcessError as e:
            output_queue.put(f"An error occurred: {e}")
            break


def rsync_data(source, dest_dir):
    cmd = ["rsync", "-av", "--progress", source, dest_dir]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    for line in iter(proc.stdout.readline, ''):
        output_queue.put(line.strip())
    du_flag, target_path = get_params(source, dest_dir)
    update_size_stats(source, target_path, du_flag)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python csrsync.py <source_file_or_directory> <destination_directory>"
            )
        print("-or-")
        print(
            "./csrsync.py <source_file_or_directory> <destination_directory>"
            )
        sys.exit(1)

    source = sys.argv[1]
    dest_dir = sys.argv[2]

    if not os.path.exists(source):
        print("Source file or directory does not exist.")
        sys.exit(1)

    rsync_thread = threading.Thread(target=rsync_data, args=(source, dest_dir))
    rsync_thread.start()

    stats_thread = threading.Thread(target=calculate_stats, args=(source, dest_dir))
    stats_thread.daemon = True
    stats_thread.start()

    stats_output = ''
    file_output = ''
    file_progress = ''
    progress_bar_str = ''

    while True:
        try:
            line = output_queue.get(timeout=1)
        except queue.Empty:
            break

        if 'Total size:' in line:
            stats_output = line
        elif '[' in line and ']' in line:
            progress_bar_str = line
        elif '%' in line:
            file_progress = line
        else:
            file_output = line

        if rsync_thread.is_alive():
            # Clear lines and re-print
            print(f"{stats_output}\033[K\n{file_output}\033[K\n{file_progress}\033[K\n{progress_bar_str}\033[K", end='', flush=True)
            # Move cursor up to the first line
            for _ in range(3):
                sys.stdout.write("\033[F")  # Cursor up one line
        else:
            # Final print, no line clear, no cursor movement
            print(f"{stats_output}\033[K\n{file_output}\033[K\n{file_progress}\033[K\n{progress_bar_str}", end='', flush=True)
            print("\033[K")
            break

        sys.stdout.flush()
