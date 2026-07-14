format_version = "2.0"

front = jbox.panel{
	graphics = { node = "Panel_front_bg" },
	widgets = {
		jbox.analog_knob{
			graphics = { node = "knob_threshold" },
			value = "/custom_properties/threshold",
		},
		jbox.toggle_button{
			graphics = { node = "SilenceSwitch" },
			value = "/custom_properties/silence_switch",
		},
		jbox.static_decoration{
			graphics = { node = "lamp_signal" },
			blend_mode = "luminance",       -- attribute RE-Blend has no model for
			ui_name = jbox.ui_text("signal lamp"),
		},
		jbox.device_name{
			graphics = { node = "DeviceName" },
		},
	},
}

back = jbox.panel{
	graphics = { node = "Panel_back_bg" },
	cable_origin = { node = "CableOrigin" },
	widgets = {
		jbox.audio_input_socket{
			graphics = { node = "MainInLeft" },
			socket = "/audio_inputs/InLeft",
		},
		jbox.audio_input_socket{
			graphics = { node = "MainInRight" },
			socket = "/audio_inputs/InRight",
		},
		jbox.device_name{
			graphics = { node = "DeviceName" },
		},
	},
}

folded_front = jbox.panel{
	graphics = { node = "Panel_folded_front_bg" },
	widgets = {
		jbox.sequence_fader{
			graphics = { node = "OnOffBypass" },
			value = "/custom_properties/builtin_onoffbypass",
			handle_size = 0,
			inverted = false,
		},
		jbox.device_name{
			graphics = { node = "DeviceName" },
		},
	},
}

folded_back = jbox.panel{
	graphics = { node = "Panel_folded_back_bg" },
	cable_origin = { node = "CableOrigin" },
	widgets = {
		jbox.device_name{
			graphics = { node = "DeviceName" },
		},
	},
}
