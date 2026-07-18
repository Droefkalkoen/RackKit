format_version = "2.0"

-- Hostile-formatting interop fixture for the patch writer (§6.2, §10.2):
-- every construct here is valid Lua that a hand editor or another tool could
-- plausibly produce, arranged to fool a naive text patcher.

--[[ long comment decoy:
knob = { offset = { 111, 222 }, { path = "knob", frames = 9 } }
]]

front = {
	Panel_front_bg = {{ path = "Panel_Front" }},
	{
		-- line comment decoy: offset = { 1, 2 }, frames = 9
		knob={offset={-10,20},{path="knob",frames=61}}, -- no-space single line
		knob_big = { offset = { 100 , 200 } ; { path = "knob_big" , frames = 31 } },
		["quoted_node"] = {
			offset = {
				5, -- x
				15 -- y
			},
			{ path = "quoted_art", frames = 2 },
		},
		label = { offset = { 7, 8 }, { path = "label -- not a comment" } },
	},
}
