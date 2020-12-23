import random
import re

__all__ = ['Congratulations']


class Congratulations:

    def __init__(self):
        self._texts = []
        with open('data/congratulations.txt', 'r') as file:
            for line in file:
                line = line.strip()
                if line:
                    self._texts.append(line)

    def get_random(self):
        ind = random.randint(0, len(self._texts) - 1)
        return self._texts[ind].replace('<br/>', '\n')
