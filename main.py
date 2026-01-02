import sys
from pathlib import Path
import io
import curses
import time
import textwrap
import re
import argparse

KEY_BACKSPACE = 127
CTRLD = 4

def effective_word_count(buffer, test_lines, precomp):
    if len(precomp) > 0 and len(precomp) == len(buffer):
        return precomp[-1], 0.0
    num_correct = 0
    num_total = 0
    word_count = 0
    for l1, l2 in zip(buffer[1:], test_lines):
        words = re.findall(r'\b\w+\b',l1) 
        word_count += len(words)
        for i in range(len(l1)):
            if l1[i] == l2[i]:
                num_correct += 1
        num_total += len(l2)
    if num_total == 0:
        return 0.0, 0.0
    return num_correct / num_total * word_count, num_correct / num_total

class TypingTest:
    def __init__(self, test_file):
        self.test_file = Path(test_file)
        self.progress_file = self.test_file.parent / ("~" + self.test_file.name) 
        self.last_pos = 0
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as pf:
                val = pf.read()
                if val.strip().isnumeric():
                    self.last_pos = int(val)
        # get the end position in file
        with open(test_file, 'r') as tf:
            tf.seek(0, io.SEEK_END)
            self.end_pos = tf.tell()
        self.tf = open(test_file, 'r')
        self.tf.seek(self.last_pos)
        self.scr = curses.initscr()
        curses.halfdelay(10)
        curses.noecho()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)
        self.c_green = curses.color_pair(1)
        self.c_red = curses.color_pair(2)
        self.c_magenta = curses.color_pair(3)
        self.c_white = curses.color_pair(4)
        self.row = 0
        self.col = 0
        self.test_lines = []
        self.line_seeks = []
        self.load_lines(self.row)
        self.wpm_win = curses.newwin(1, curses.COLS, curses.LINES - 1, 0)
        self.precomp_wc = []
        self.buffer = [""] 
        self.start_time = 0.0
        self.num_previous = 3
        
    def run(self):
        s = ""
        self.add_lines(self.test_lines[self.row:])
        skip_next = False
        while True:
            char = self.scr.getch()
            if char != curses.ERR:
                if self.start_time == 0.0:
                    self.start_time = time.time()
                if skip_next:
                    skip_next = False
                    continue
                if char == KEY_BACKSPACE:
                    self.col -= 1
                    if self.col < 0 and self.row > 0:
                        self.scr.clear()
                        self.row -= 1
                        self.add_lines(self.test_lines[self.row:])
                        s = self.buffer.pop()[:-1]
                        self.col = len(s) 
                    else:
                        self.col = max(self.col, 0)
                        s = s[:self.col]
                elif char == CTRLD:
                    # skip next 10 lines 
                    skip_next = True
                    # increment the line
                    self.scr.clear()
                    self.row += 1
                    if self.row == len(self.test_lines):
                        return
                    self.col = 0
                    self.buffer.append(s)
                    s = ""
                    self.out_diff_line(s, self.row)
                    self.load_lines(self.row)
                    self.add_lines(self.test_lines[self.row:])
                else:
                    s += chr(char)
                    self.col += 1
                self.out_diff_line(s, self.row)
                if self.col == len(self.test_lines[self.row]):
                    skip_next = True
                    # increment the line
                    self.scr.clear()
                    self.row += 1
                    if self.row == len(self.test_lines):
                        return
                    self.col = 0
                    self.buffer.append(s)
                    s = ""
                    self.out_diff_line(s, self.row)
                    self.load_lines(self.row)
                    self.add_lines(self.test_lines[self.row:])
                self.scr.addstr(self.num_previous, self.col, self.test_lines[self.row][self.col], self.c_white | curses.A_UNDERLINE)
                self.scr.addstr(self.num_previous, self.col+1, self.test_lines[self.row][self.col+1:], self.c_white)
            self.update_wpm_str(char) 

    def update_wpm_str(self, char):
        word_count, acc = effective_word_count(self.buffer, self.test_lines[:self.row], self.precomp_wc)
        wpm = 60 * word_count / (time.time() - self.start_time)
        completed = self.last_pos / self.end_pos * 100
        self.wpm_win.addstr(0, 0, f"wpm: {wpm:3.2f} | completed: {completed:3.1f}% | accuracy: {100*acc:3.1f}% | {char:4d}", self.c_magenta) 
        self.wpm_win.refresh()
        
    def load_lines(self, row):
        while len(self.test_lines) - row < self.main_lines:
            line = self.tf.readline()
            if line.strip() == "":
                continue
            if 0 <= row-1 < len(self.line_seeks) and self.last_pos < self.line_seeks[row-1]:
                with open(self.progress_file, 'w') as pf:
                    pf.write(str(self.line_seeks[row-1]))
            pos = self.tf.tell()
            line = " ".join([w.strip() for w in line.split(' ') if w.strip() != ""])
            wrapped = textwrap.wrap(line, width = curses.COLS, tabsize=4)
            self.test_lines.extend(wrapped)
            self.line_seeks.extend([pos for _ in wrapped])

    def out_diff_line(self, s, row):
        for j in range(1,min(self.num_previous, len(self.buffer))+1):
            for i in range(len(self.buffer[-j])):
                good = self.buffer[-j][i] == self.test_lines[row-j][i]
                self.scr.addstr(self.num_previous-j, i, self.test_lines[row-j][i], self.c_green if good else self.c_red)
        for i in range(len(s)):
            good = s[i] == self.test_lines[row][i]
            self.scr.addstr(self.num_previous, i, self.test_lines[row][i], self.c_green if good else self.c_red)
    
    def add_lines(self, lines):
        for i, l in enumerate(lines[:self.main_lines-self.num_previous-1]):
            self.scr.addstr(i+self.num_previous, 0, l, self.c_white)
    
    @property
    def main_lines(self):
        return curses.LINES - 1
def main():
    parser = argparse.ArgumentParser(
            prog="typingtest",
            description="commandline typing practice with custom text"
            )
    parser.add_argument('test_file')
    args = parser.parse_args()
    test_file = args.test_file

    tt = TypingTest(test_file)
    tt.run()

if __name__ == "__main__":
    main()
