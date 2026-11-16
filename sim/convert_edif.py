import argparse
from pathlib import Path
import re

import spydrnet as sdn
from spydrnet.flatten import flatten
from spydrnet.uniquify import uniquify


ROOT = Path(__file__).resolve().parents[1]
SYNTHESIS_PROPERTIES = {
    "SOFT_HLUTNM", "HLUTNM", "FSM_ENCODED_STATES", "FSM_ENCODING",
    "METHODOLOGY_DRC_VIOS", "XILINX_LEGACY_PRIM", "KEEP", "RTL_KEEP",
}
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*\Z")
BUS_NAME = re.compile(r"(.+)\[(\d+):(\d+)\]\Z")


def verilog_name(name):
    # 转义标识符仍不能包含空白或可终止标识符的反斜杠，防止网表注入生成代码。
    if not re.fullmatch(r"[A-Za-z0-9_$./:<>()\[\]{}+*=-]+", name):
        raise ValueError(f"不安全的 EDIF 标识符：{name!r}")
    return name if IDENTIFIER.fullmatch(name) else "\\" + name + " "


def convert(source, destination):
    netlist = sdn.parse(str(source))
    # 展平内部模块边界，生成两个仿真器均支持的普通端口声明。
    uniquify(netlist)
    flatten(netlist)
    primitives = set()
    init_count = 0
    for library in netlist.libraries:
        for definition in library.definitions:
            for port in definition.ports:
                match = BUS_NAME.fullmatch(port.name)
                if match:
                    name, high, low = match.groups()
                    high, low = int(high), int(low)
                    if high < low or len(port.pins) != high - low + 1:
                        raise ValueError(f"Unsupported port range: {port.name}")
                    # EDIF member 0 对应最高位；Verilog composer 的 pin 0 对应最低位。
                    port.pins = list(reversed(port.pins))
                    port.lower_index = low
                    port.name = name
                elif len(port.pins) > 1:
                    raise ValueError(f"Missing bus range: {port.name}")

                if library.name != "hdi_primitives":
                    # 综合会移除未使用输入的连线，保留完整的模块端口宽度。
                    cable = next((c for c in definition.cables if c.name == port.name), None)
                    for index, pin in enumerate(port.pins):
                        if pin.wire is None:
                            if cable is None:
                                cable = definition.create_cable(name=port.name)
                                cable.lower_index = port.lower_index
                                cable.create_wires(len(port.pins))
                            if cable.lower_index != port.lower_index or len(cable.wires) > len(port.pins):
                                raise ValueError(f"Port/cable width mismatch: {port.name}")
                            if len(cable.wires) < len(port.pins):
                                cable.create_wires(len(port.pins) - len(cable.wires))
                            cable.wires[index].connect_pin(pin)

            for instance_index, instance in enumerate(definition.children):
                # 用独立悬空线保留未连接 pin 在拼接中的位置。
                for pin_index, pin in enumerate(instance.pins.values()):
                    if pin.wire is None:
                        cable = definition.create_cable(name=f"__open_{instance_index}_{pin_index}")
                        cable.create_wire().connect_pin(pin)
                parameters = {}
                for prop in instance.get("EDIF.properties", []):
                    key = prop["identifier"]
                    if key == "INIT" or key.startswith("IS_"):
                        value = str(prop["value"])
                        if not re.fullmatch(r"(?:[0-9]+|[0-9]+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+)", value):
                            raise ValueError(f"不安全的 EDIF 数值属性：{key}={value!r}")
                        if not re.fullmatch(r"(?:INIT|IS_[A-Za-z0-9_]+)", key):
                            raise ValueError(f"不安全的 EDIF 属性名：{key!r}")
                        parameters[key] = value
                        init_count += key == "INIT"
                    elif key not in SYNTHESIS_PROPERTIES:
                        raise ValueError(f"Unclassified EDIF property: {key} on {instance.name}")
                if parameters:
                    instance["VERILOG.Parameters"] = parameters
                if instance.reference.library.name == "hdi_primitives":
                    primitives.add(instance.reference.name)

            for element in [definition, *definition.ports, *definition.cables, *definition.children]:
                element.name = verilog_name(element.name)

    sdn.compose(netlist, str(destination),
                definition_list=[netlist.top_instance.reference.name], write_blackbox=False)
    print(f"{source.name} -> {destination}; INIT={init_count}; "
          f"primitives={','.join(sorted(primitives))}")


def main():
    parser = argparse.ArgumentParser(description="Convert supplied Vivado EDIF netlists to Verilog")
    parser.add_argument("--output", type=Path, default=ROOT / ".sim" / "netlist")
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted((ROOT / "edf_file").glob("*.edf")):
        convert(source, destination / (source.stem + ".v"))


if __name__ == "__main__":
    main()
