format_version = "3.0"

-- Motherboard for the silence_detector fixture. RE-Blend reads this file
-- read-only and best-effort (design §4.1): only stepped properties matter,
-- for the frames-vs-steps validation check.

custom_properties = jbox.property_set{
	document_owner = {
		properties = {
			threshold = jbox.number{
				property_tag = 1,
				default = 0.5,
				ui_name = jbox.ui_text("threshold"),
				ui_type = jbox.ui_percent(),
			},
			silence_switch = jbox.boolean{
				property_tag = 2,
				default = false,
				ui_name = jbox.ui_text("silence switch"),
				ui_type = jbox.ui_selector{ jbox.ui_text("off"), jbox.ui_text("on") },
			},
			-- a stepped selector nothing in hdgui_2D binds yet; exercises the
			-- steps reader without tripping the frames-vs-steps check
			mode = jbox.number{
				property_tag = 3,
				default = 0,
				steps = 4,
				ui_name = jbox.ui_text("mode"),
			},
		},
	},
	rt_owner = {
		properties = {
			silence = jbox.boolean{ property_tag = 10, default = false },
		},
	},
}

audio_inputs = {
	InLeft = jbox.audio_input{ ui_name = jbox.ui_text("in left") },
	InRight = jbox.audio_input{ ui_name = jbox.ui_text("in right") },
}
