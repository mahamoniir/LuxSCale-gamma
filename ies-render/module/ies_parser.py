import os
from collections import deque, namedtuple
import math
import platform


class BrokenIESFileError(Exception):
    """Exception raised for errors in the IES file format."""

    def __init__(self, message="IES file is broken"):
        self.message = message
        super().__init__(self.message)


def get_next_numbers(f, count):
    """
    Retrieve a specified amount of numeric values from a file stream.

    This function reads lines from the provided file stream, splits them
    into whitespace-separated strings, and accumulates the numeric values.
    It continues to read lines until the specified amount of numbers is
    collected or the file ends. If the file ends before enough numbers
    are gathered, it raises a BrokenIESFileError.

    Args:
        f (file): A file stream object opened in text mode.
        count (int): The number of numeric values to retrieve from the file stream.

    Returns:
        list[str]: A list containing `count` string representations of the numbers.

    Raises:
        BrokenIESFileError: If the end of file is reached before `count` numbers are retrieved.
    """
    numbers = []
    while len(numbers) < count:
        line = next(f, None)
        if line is None:
            raise BrokenIESFileError("Unexpected end of file while reading numbers")
        numbers.extend(line.split())
    return numbers[:count]


# LM-63 photometric_type code (field index 5 on the data line after TILT=)
#   1 = Type C (most common; γ from nadir, C-plane azimuth 0–360°)
#   2 = Type B (lateral rotation; β vertical, B horizontal −90…+90°)
#   3 = Type A (automotive/horizontal; α elevation, A horizontal sweep)
_PHOTOMETRIC_TYPE_NAMES = {1: "C", 2: "B", 3: "A"}
_VERTICAL_ANGLE_LABELS = {
    1: "gamma",
    2: "beta",
    3: "alpha",
}
_HORIZONTAL_ANGLE_LABELS = {
    1: "C",
    2: "B",
    3: "A",
}


def photometric_type_name(code) -> str:
    """Return ``"C" | "B" | "A" | "Unknown"`` for an LM-63 photometric_type code."""
    try:
        return _PHOTOMETRIC_TYPE_NAMES.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def vertical_angle_label_for_type(code) -> str:
    """Return ``gamma/beta/alpha`` label for the LM-63 photometric type."""
    try:
        return _VERTICAL_ANGLE_LABELS.get(int(code), "gamma")
    except (TypeError, ValueError):
        return "gamma"


def horizontal_angle_label_for_type(code) -> str:
    """Return ``C/B/A`` label for the LM-63 photometric type."""
    try:
        return _HORIZONTAL_ANGLE_LABELS.get(int(code), "C")
    except (TypeError, ValueError):
        return "C"


IESData = namedtuple(
    "IESData",
    [
        "vertical_angles",  # list of vertical angles
        "horizontal_angles",  # list of horizontal angles
        "candela_values",  # {horizontal_angle: [candela_values]}
        "max_value",  # max value of candela_values (float)
        "num_lamps",  # number of lamps (int)
        "lumens_per_lamp",  # lumens per lamp (float)
        "multiplier",  # multiplier (float)
        "width",  # width (float)
        "length",  # length (float)
        "height",  # height (float)
        "shape",  # shape (str)
        "photometric_type",  # LM-63 code: 1=C, 2=B, 3=A (int)
        "photometric_type_name",  # "C" | "B" | "A" | "Unknown"
        "vertical_angle_label",  # "gamma" | "beta" | "alpha"
        "horizontal_angle_label",  # "C" | "B" | "A"
    ],
    # Defaults keep older positional callers (e.g. photometry_ies_adapter) working.
    defaults=(1, "C", "gamma", "C"),
)


class IES_Parser:
    """
    Eager parsing IES file
    Returns IESData namedtuple
    """

    def __init__(self, ies_path: str):
        self._ies_path = ies_path
        if self._ies_path and os.path.exists(self._ies_path):
            self._ies_data = self._parse()
        else:
            raise FileNotFoundError("IES file not found")

    def _parse(self) -> IESData:
        def _parse_line(line: str) -> deque:
            cleaned_line = line.replace(",", " ")
            return deque(map(float, cleaned_line.split()))

        with open(
            self._ies_path,
            "r",
            encoding="Windows-1252" if platform.system() != "Windows" else None,
        ) as f:
            tilt_found = False
            for line in f:
                stripped = line.strip()
                if not stripped.startswith("TILT="):
                    continue
                tilt_found = True
                if stripped != "TILT=NONE":
                    raise BrokenIESFileError(
                        f"Unsupported TILT value: {stripped} (only TILT=NONE is handled)"
                    )
                break
            if not tilt_found:
                raise BrokenIESFileError("TILT= line not found")

            # * Get sizes and other data (13 numbers)
            light_data = get_next_numbers(f, 13)  # f.readline().split()
            num_lamps = int(light_data[0])
            lumens_per_lamp = float(light_data[1])
            multiplier = float(light_data[2])
            num_vertical_angles = int(light_data[3])
            num_horizontal_angles = int(light_data[4])
            # LM-63 photometric_type is on index [5] of the data line right after TILT=:
            #   1 = Type C, 2 = Type B, 3 = Type A.
            try:
                photometric_type = int(float(light_data[5]))
            except (TypeError, ValueError):
                photometric_type = 1  # conservative fallback
            if photometric_type not in (1, 2, 3):
                photometric_type = 1
            ptype_name = _PHOTOMETRIC_TYPE_NAMES.get(photometric_type, "C")
            vertical_angle_label = vertical_angle_label_for_type(photometric_type)
            horizontal_angle_label = horizontal_angle_label_for_type(photometric_type)
            unit = int(light_data[6])  # 1 - feet, 2 - meters
            k = 1 if unit == 2 else 0.3048
            width = float(light_data[7]) * k
            length = float(light_data[8]) * k
            height = float(light_data[9]) * k
            # TODO (all types of shapes)
            if all(i == 0 for i in [width, length, height]):
                shape = "point"
            elif height == 0 and width < 0 and width == length:
                shape = "circular"
            elif height == 0 and width < 0 and width != length:
                shape = "ellipse"
            elif height != 0 and width < 0 and width == length:
                shape = "vertical cylinder"
            elif height != 0 and width != length and length < 0:
                shape = "vertical ellipsoidal cylinder"
            elif height < 0 and width == length == height:
                shape = "sphere"
            elif height < 0 and width < 0 and length < 0:
                shape = "ellipsoidal spheroid"
            elif height == 0:
                shape = "rectangular"
            else:
                shape = "rectangular with luminous sides"

            # * Read vertical angles
            vertical_angles, horizontal_angles, candela_values = (
                deque(),
                deque(),
                deque(),
            )

            while len(vertical_angles) < num_vertical_angles:
                line = f.readline()
                if not line:
                    raise BrokenIESFileError(
                        "Unexpected EOF while reading vertical angles"
                    )
                vertical_angles.extend(_parse_line(line))
            vertical_angles = list(vertical_angles)[:num_vertical_angles]
            # Angle-range sanity: branch on photometric type so Type B / Type A files
            # aren't rejected under Type-C-only rules (see documentation/ies_types.md).
            v_first = int(vertical_angles[0])
            v_last = int(vertical_angles[-1])
            if photometric_type == 1:
                # Type C: γ measured from nadir, 0–180° (full) or 0–90° / 90–180° (hemisphere).
                if v_first not in (0, 90) or v_last not in (90, 180):
                    raise BrokenIESFileError(
                        f"Type C vertical range invalid: {v_first}..{v_last}"
                    )
            else:
                # Type B (β) / Type A (α) span −90…+90° (or 0…90°).
                if v_first not in (-90, 0, 90) or v_last not in (-90, 0, 90, 180):
                    raise BrokenIESFileError(
                        f"Type {ptype_name} vertical range invalid: {v_first}..{v_last}"
                    )

            # * Read horizontal angles
            while len(horizontal_angles) < num_horizontal_angles:
                line = f.readline()
                if not line:
                    raise BrokenIESFileError(
                        "Unexpected EOF while reading horizontal angles"
                    )
                horizontal_angles.extend(_parse_line(line))
            horizontal_angles = list(horizontal_angles)[:num_horizontal_angles]
            h_first = int(horizontal_angles[0])
            h_last = int(horizontal_angles[-1])
            if photometric_type == 1:
                # Type C: C-plane azimuth 0…360° with common symmetric reductions.
                if h_first not in (0, -90) or h_last not in (0, 90, 180, 360):
                    raise BrokenIESFileError(
                        f"Type C horizontal range invalid: {h_first}..{h_last}"
                    )
            elif photometric_type == 2:
                # Type B: B-plane −90…+90° (symmetric files often 0…90°).
                if h_first not in (-90, 0) or h_last not in (0, 90):
                    raise BrokenIESFileError(
                        f"Type B horizontal range invalid: {h_first}..{h_last}"
                    )
            else:
                # Type A: A-plane 0…360° typical; some files use −90…+90°.
                if h_first not in (-90, 0) or h_last not in (0, 90, 180, 360):
                    raise BrokenIESFileError(
                        f"Type A horizontal range invalid: {h_first}..{h_last}"
                    )

            # * Read candela values
            needed_candela_values = num_vertical_angles * num_horizontal_angles
            while len(candela_values) < needed_candela_values:
                line = f.readline()
                if not line:
                    raise BrokenIESFileError(
                        "Unexpected EOF while reading candela values"
                    )
                candela_values.extend(_parse_line(line))

            candela_values = list(candela_values)[:needed_candela_values]
            max_value = max(candela_values)

            # * assert len(vert_angles)*len(horizontal_angles) == len(candelas)
            if len(vertical_angles) * len(horizontal_angles) != len(candela_values):
                raise BrokenIESFileError()

            V = len(candela_values) // len(horizontal_angles)
            candela_values_dct = {
                n: candela_values[i * V : (i + 1) * V]
                for i, n in enumerate(horizontal_angles)
            }

            return IESData(
                vertical_angles,
                horizontal_angles,
                candela_values_dct,
                max_value,
                num_lamps,
                lumens_per_lamp,
                multiplier,
                math.fabs(width),
                math.fabs(length),
                math.fabs(height),
                shape,
                photometric_type,
                ptype_name,
                vertical_angle_label,
                horizontal_angle_label,
            )

    @property
    def ies_data(self) -> IESData:
        return self._ies_data

    @property
    def vertical_angle_name(self) -> str:
        """Physical vertical angle axis name for this file type."""
        return getattr(self._ies_data, "vertical_angle_label", "gamma")

    @property
    def horizontal_angle_name(self) -> str:
        """Physical horizontal angle axis name for this file type."""
        return getattr(self._ies_data, "horizontal_angle_label", "C")

    def __repr__(self) -> str:
        if not self._ies_data:
            return "Broken file"

        bold = "\033[1m"
        underline = "\033[4m"
        red = "\033[91m"  # Red color
        green = "\033[92m"  # Green color
        yellow = "\033[93m"  # Yellow color
        blue = "\033[94m"  # Blue color
        reset = "\033[0m"
        message = f"IES file: {underline}{blue}{self._ies_path}{reset}\n"
        ptype_name = getattr(self._ies_data, "photometric_type_name", "C")
        ptype_code = getattr(self._ies_data, "photometric_type", 1)
        message += (
            f"{bold}Photometric type:\t{yellow}Type {ptype_name}{reset}"
            f" (LM-63 code {ptype_code})\n"
        )
        message += f"{bold}Shape:\t{self._ies_data.shape}, L={self._ies_data.length}m, H={self._ies_data.height}m{reset}\n"
        va = self._ies_data.vertical_angles
        if len(va) >= 2:
            vert_str = f"{va[0]}, {va[1]}, ... {va[-1]} [{len(va)} values]\n"
        elif len(va) == 1:
            vert_str = f"{va[0]} [1 value]\n"
        else:
            vert_str = "[no values]\n"
        v_label = getattr(self._ies_data, "vertical_angle_label", "gamma")
        h_label = getattr(self._ies_data, "horizontal_angle_label", "C")
        message += f"{bold}{underline}{green}Vertical ({v_label}):{reset}\n\t" + vert_str

        if len(self._ies_data.horizontal_angles) == 1:
            first_h = self._ies_data.horizontal_angles[0]
            hor_str = f"{first_h}\n"
            message += f"{bold}{underline}{green}Horizontal ({h_label}):{reset}\n\t" + hor_str
            message += f"{bold}{underline}{green}Candela:{reset}\n\t" + ", ".join(
                map(str, self._ies_data.candela_values[first_h])
            )
        else:
            def _fmt_angle(a: float) -> str:
                af = float(a)
                return str(int(af)) if af.is_integer() else str(af)

            hor_str = f"{self._ies_data.horizontal_angles[0]}, {self._ies_data.horizontal_angles[1]}, ... {self._ies_data.horizontal_angles[-1]} [{len(self.ies_data.horizontal_angles)} values]\n"
            message += f"{bold}{underline}{green}Horizontal ({h_label}):{reset}\n\t" + hor_str

            message += f"{bold}{underline}{green}Candela:{reset}\n"
            start_h = self._ies_data.horizontal_angles[0]
            end_h = self._ies_data.horizontal_angles[-1]
            message += f"\t{bold}{yellow}{_fmt_angle(start_h)}:{reset}\t" + ", ".join(
                map(str, self._ies_data.candela_values[start_h])
            )
            message += f"\n\t{bold}...{reset}\n"
            message += f"\n\t{bold}{yellow}{_fmt_angle(end_h)}:{reset}\t" + ", ".join(
                map(str, self._ies_data.candela_values[end_h])
            )
            message += "\n"
        return message

    def __call__(self) -> IESData:
        return self._ies_data


if __name__ == "__main__":
    import sys

    argv = [a for a in sys.argv[1:] if a.strip()]
    type_only = False
    paths = []
    for arg in argv:
        if arg in ("--type", "-t"):
            type_only = True
        else:
            paths.append(arg)

    if not paths:
        # Default demo paths (same as before) when no CLI arg is given.
        paths = [
            "examples/ies-lights-pack/defined-diffuse-spot.ies",
            "examples/ies-lights-pack/star-focused.ies",
        ]

    for p in paths:
        try:
            ies = IES_Parser(p)
        except FileNotFoundError:
            print(f"{p}\tNOT FOUND")
            continue
        except BrokenIESFileError as ex:
            print(f"{p}\tBROKEN ({ex})")
            continue

        d = ies.ies_data
        if type_only:
            print(
                f"{p}\ttype={d.photometric_type} ({d.photometric_type_name})"
                f"\tV_label={d.vertical_angle_label}"
                f"\tH_label={d.horizontal_angle_label}"
                f"\tV={len(d.vertical_angles)} [{d.vertical_angles[0]}..{d.vertical_angles[-1]}]"
                f"\tH={len(d.horizontal_angles)} [{d.horizontal_angles[0]}..{d.horizontal_angles[-1]}]"
            )
        else:
            print(ies)
