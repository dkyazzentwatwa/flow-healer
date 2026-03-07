from flow_healer.cli import build_parser


def test_doctor_parser_accepts_preflight_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["doctor", "--preflight"])

    assert args.command == "doctor"
    assert args.preflight is True
