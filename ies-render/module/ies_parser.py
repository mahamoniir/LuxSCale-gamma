import os
from collections import namedtuple
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
        numbers.extend(line.replace(",", " ").split())
    return numbers[:count]


# LM-63 photometric type codes:
#   1 = Type C (gamma + C-plane azimuth)
#   2 = Type B (beta + B-plane)
#   3 = Type A (alpha + A-plane)
PHOTOMETRIC_TYPE_NAMES = {1: "C", 2: "B", 3: "A"}
VERTICAL_ANGLE_LABELS = {1: "gamma", 2: "beta", 3: "alpha"}
HORIZONTAL_ANGLE_LABELS = {1: "C", 2: "B", 3: "A"}


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
        "photometric_type",  # LM-63 code: 1=C, 2=B, 3=A
        "photometric_type_name",  # "C" / "B" / "A"
        "vertical_angle_label",  # gamma / beta / alpha
        "horizontal_angle_label",  # C / B / A
    ],
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
        with open(
            self._ies_path,
            "r",
            encoding="Windows-1252" if platform.system() != "Windows" else None,
            errors="replace",
        ) as f:
            tilt_value = None
            for line in f:
                stripped = line.strip()
                if stripped.startswith("TILT="):
                    tilt_value = stripped
                    break
            if tilt_value is None:
                raise BrokenIESFileError("TILT= line not found")
            if tilt_value != "TILT=NONE":
                raise BrokenIESFileError(
                    f"Unsupported TILT value: {tilt_value} (only TILT=NONE is handled)"
                )

            # * Get sizes and other data (13 numbers)
            light_data = get_next_numbers(f, 13)
            try:
                num_lamps = int(float(light_data[0]))
                lumens_per_lamp = float(light_data[1])
                multiplier = float(light_data[2])
                num_vertical_angles = int(float(light_data[3]))
                num_horizontal_angles = int(float(light_data[4]))
                photometric_type = int(float(light_data[5]))
                unit = int(float(light_data[6]))  # 1 - feet, 2 - meters
                raw_width = float(light_data[7])
                raw_length = float(light_data[8])
                raw_height = float(light_data[9])
            except (TypeError, ValueError):
                raise BrokenIESFileError("Malformed photometric header values")

            if photometric_type not in (1, 2, 3):
                photometric_type = 1
            photometric_type_name = PHOTOMETRIC_TYPE_NAMES.get(photometric_type, "C")
            vertical_angle_label = VERTICAL_ANGLE_LABELS.get(photometric_type, "gamma")
            horizontal_angle_label = HORIZONTAL_ANGLE_LABELS.get(photometric_type, "C")

            k = 1.0 if unit == 2 else 0.3048
            width = abs(raw_width) * k
            length = abs(raw_length) * k
            height = abs(raw_height) * k
            # TODO (all types of shapes)
            if all(i == 0 for i in [raw_width, raw_length, raw_height]):
                shape = "point"
            elif raw_height == 0 and raw_width < 0 and raw_width == raw_length:
                shape = "circular"
            elif raw_height == 0 and raw_width < 0 and raw_width != raw_length:
                shape = "ellipse"
            elif raw_height != 0 and raw_width < 0 and raw_width == raw_length:
                shape = "vertical cylinder"
            elif raw_height != 0 and raw_width != raw_length and raw_length < 0:
                shape = "vertical ellipsoidal cylinder"
            elif raw_height < 0 and raw_width == raw_length == raw_height:
                shape = "sphere"
            elif raw_height < 0 and raw_width < 0 and raw_length < 0:
                shape = "ellipsoidal spheroid"
            elif raw_height == 0:
                shape = "rectangular"
            else:
                shape = "rectangular with luminous sides"

            # * Read vertical angles
            vertical_angles = [float(v) for v in get_next_numbers(f, num_vertical_angles)]
            if len(vertical_angles) != num_vertical_angles:
                raise BrokenIESFileError("Unexpected vertical angle count")

            # * Read horizontal angles
            horizontal_angles = [float(h) for h in get_next_numbers(f, num_horizontal_angles)]
            if len(horizontal_angles) != num_horizontal_angles:
                raise BrokenIESFileError("Unexpected horizontal angle count")

            # * Read candela values
            expected_candela_count = num_vertical_angles * num_horizontal_angles
            candela_values = [float(c) for c in get_next_numbers(f, expected_candela_count)]
            if len(candela_values) != expected_candela_count:
                raise BrokenIESFileError("Unexpected candela value count")

            # Apply multiplier to candela values per IES LM-63.
            if abs(multiplier - 1.0) > 1e-9:
                candela_values = [c * multiplier for c in candela_values]
            max_value = max(candela_values) if candela_values else 0.0

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
                float(width),
                float(length),
                float(height),
                shape,
                int(photometric_type),
                str(photometric_type_name),
                str(vertical_angle_label),
                str(horizontal_angle_label),
            )

    @property
    def ies_data(self) -> IESData:
        return self._ies_data

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
        message += f"{bold}Shape:\t{self._ies_data.shape}, L={self._ies_data.length}m, H={self._ies_data.height}m{reset}\n"
        message += (
            f"{bold}Photometric type:\t"
            f"{self._ies_data.photometric_type_name} "
            f"(code {self._ies_data.photometric_type}){reset}\n"
        )
        vert_str = f"{self._ies_data.vertical_angles[0]}, {self._ies_data.vertical_angles[1]}, ... {self._ies_data.vertical_angles[-1]} [{len(self.ies_data.vertical_angles)} values]\n"
        message += f"{bold}{underline}{green}Vertical:{reset}\n\t" + vert_str

        if len(self._ies_data.horizontal_angles) == 1:
            hor_str = f"{self._ies_data.horizontal_angles[0]}\n"
            message += f"{bold}{underline}{green}Horizontal:{reset}\n\t" + hor_str
            start_h = self._ies_data.horizontal_angles[0]
            message += f"{bold}{underline}{green}Candela:{reset}\n\t" + ", ".join(
                map(str, self._ies_data.candela_values[start_h])
            )
        else:
            hor_str = f"{self._ies_data.horizontal_angles[0]}, {self._ies_data.horizontal_angles[1]}, ... {self._ies_data.horizontal_angles[-1]} [{len(self.ies_data.horizontal_angles)} values]\n"
            message += f"{bold}{underline}{green}Horizontal:{reset}\n\t" + hor_str

            message += f"{bold}{underline}{green}Candela:{reset}\n"
            start_h = self._ies_data.horizontal_angles[0]
            end_h = self._ies_data.horizontal_angles[-1]
            message += f"\t{bold}{yellow}{int(start_h)}:{reset}\t" + ", ".join(
                map(str, self._ies_data.candela_values[start_h])
            )
            message += f"\n\t{bold}...{reset}\n"
            message += f"\n\t{bold}{yellow}{int(end_h)}:{reset}\t" + ", ".join(
                map(str, self._ies_data.candela_values[end_h])
            )
            message += "\n"
        return message

    def __call__(self) -> IESData:
        return self._ies_data


if __name__ == "__main__":
    ies_path = "examples/ies-lights-pack/defined-diffuse-spot.ies"
    ies_path = "examples/ies-lights-pack/star-focused.ies"
    # ies_path = "examples/horiz_angles.ies"
    ies = IES_Parser(ies_path)
    print(ies)
