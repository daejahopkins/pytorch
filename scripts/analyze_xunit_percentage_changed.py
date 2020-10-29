#!/usr/bin/env python

import argparse
import os
import sys

try:
    from junitparser import JUnitXml, TestSuite
except ImportError:
    raise ImportError(
        "junitparser not found, please install with 'pip install junitparser'",
        file=sys.stderr
    )

try:
    from tqdm import tqdm
except ImportError:
    print(
        "Warning: Module tqdm not found, no progress bars will be displayed",
        file=sys.stderr,
    )
    tqdm = iter


class ThresholdExceeded(Exception):
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze pytorch unit test xunit output",
    )
    parser.add_argument(
        "base", help="Base xunit reports (single file or directory) to compare to"
    )
    parser.add_argument(
        "compare_to", help="xunit reports (single file or directory) to compare to base"
    )
    parser.add_argument(
        "-t",
        "--threshold",
        default=10,
        help="Percentage increase allowed for test time difference",
    )
    return parser.parse_args()


def parse_junit_reports(path_to_reports):
    if not os.path.exists(path_to_reports):
        raise FileNotFoundError(f"Path '{path_to_reports}', not found")
    # Return early if the path provided is just a file
    if os.path.isfile(path_to_reports):
        ret_xml = JUnitXml.fromfile(path_to_reports)
    elif os.path.isdir(path_to_reports):
        ret_xml = JUnitXml()
        for root, _, files in os.walk(path_to_reports):
            for file in tqdm([f for f in files if f.endswith("xml")]):
                ret_xml += JUnitXml.fromfile(os.path.join(root, file))
    return convert_junit_to_dict(ret_xml)


def convert_junit_to_dict(xml):
    tests = dict()
    for item in xml:
        if isinstance(item, TestSuite):
            tests.update(convert_junit_to_dict(item))
        else:
            tests[f"{xml.name}.{item.classname}.{item.name}"] = item.time
    return tests


def calculate_changed(base, compare_to):
    both = set(base.keys()).intersection(compare_to.keys())
    changed = dict()
    # Calculating percentage changed
    for key in both:
        # Don't divide by zero
        if base[key] == 0:
            changed[key] = 0
        else:
            changed[key] = ((compare_to[key] - base[key]) / base[key]) * 100
    return changed


def main():
    options = parse_args()
    base = parse_junit_reports(options.base)
    compare_to = parse_junit_reports(options.compare_to)
    changed = calculate_changed(base, compare_to)
    over_threshold = {k: v for k, v in changed.items() if v > options.threshold}
    # TODO: Construct a junit xml for failed thresholds
    if over_threshold:
        raise ThresholdExceeded(
            "Test time increase threshold exceeded for the following testcases:\n"
            f"{over_threshold}"
        )

    additive = set(compare_to.keys()).difference(base.keys())
    total_time_base = sum(base.values())
    total_time_compare = sum(compare_to.values())
    total_percentage_changed = (
        (total_time_compare - total_time_base) / total_time_base * 100
    )
    if total_percentage_changed > options.threshold:
        added_time = {k: compare_to[k] for k in additive}
        raise ThresholdExceeded(
            "Total test time increase threshold exceeded, added tests (in seconds):\n",
            f"{added_time}",
        )


if __name__ == "__main__":
    main()
