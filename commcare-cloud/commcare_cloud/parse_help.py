from collections import namedtuple
import subprocess


def filtered_help_message(command, below_line, exclude_args, above_line=None):
    """

    :param command: command whose output should be parsed, e.g. 'ansible -h'
    :param below_line: line to trigger parsing;
        everything up to and including this line will be ignored
    :param exclude_args: list of args to exclude (short or long form)
        e.g. ['-m', '-b', '--become-user']
        fails hard if any of these args are not found
    :return:
    """
    large_indent = '                        '
    not_started, looking_for_arg, found_arg, traversing_arg_lines, eof = range(5)
    output = subprocess.check_output(command, shell=True)
    Section = namedtuple('Section', 'arg_names lines')

    class FSA(object):
        def __init__(self, lines):
            # arg_name : section_number
            self.remaining_lines = list(reversed(lines))
            self.section_index = {}
            self.sections = []
            self.working_section = None
            self.state = not_started

        def finalize_working_section(self):
            if self.working_section:
                for arg_name in self.working_section.arg_names:
                    self.section_index[arg_name] = len(self.sections)
                self.sections.append(self.working_section.lines)
            self.working_section = None

        def new_arg_section(self, arg_names):
            self.finalize_working_section()
            self.working_section = Section(arg_names, [])

        def new_fluff_section(self):
            self.finalize_working_section()
            self.working_section = Section((), [])

        def peek(self):
            try:
                return self.remaining_lines[-1]
            except IndexError:
                self.state = eof
                return None

        def consume_line(self):
            self.working_section.lines.append(self.remaining_lines.pop())

        def discard_line(self):
            self.remaining_lines.pop()

        def get_filtered_help_message(self, exclude_args):
            exclude_section_numbers = {self.section_index[arg_name]
                                       for arg_name in exclude_args}

            def yield_lines():
                for i, section in enumerate(self.sections):
                    if i not in exclude_section_numbers:
                        for line in section:
                            yield line

            return '\n'.join(yield_lines())

    fsa = FSA(output.splitlines())
    while True:
        line = fsa.peek()
        if fsa.state is not not_started and line and line == above_line:
            fsa.state = eof

        if fsa.state is not_started:
            fsa.discard_line()
            if line == below_line:
                fsa.new_fluff_section()
                fsa.state = looking_for_arg
        elif fsa.state is looking_for_arg:
            if not line.startswith(large_indent) and line.lstrip().startswith('-'):
                fsa.state = found_arg
            else:
                fsa.consume_line()
        elif fsa.state is found_arg:
            # example line:
            # '    -s, --sudo          run operations with sudo (nopasswd) (deprecated, use'
            # parse ['-s', '--sudo']
            fsa.new_arg_section([
                part.strip().split(' ')[0].split('=')[0]
                for part in line.strip().split('  ')[0].split(',')
            ])
            fsa.consume_line()
            fsa.state = traversing_arg_lines
        elif fsa.state is traversing_arg_lines:
            if line.startswith(large_indent):
                fsa.consume_line()
            elif line.lstrip().startswith('-'):
                fsa.state = found_arg
            else:
                fsa.new_fluff_section()
                fsa.state = looking_for_arg
        elif fsa.state is eof:
            fsa.finalize_working_section()
            break

    return fsa.get_filtered_help_message(exclude_args)
