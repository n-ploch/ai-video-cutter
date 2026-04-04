"""Default prompt templates for video analysis stages."""

GLOBAL_ANALYSIS_PROMPT = """\
You are a Professional Video Editor and Colorist. Watch the entire video \
before responding.

Return a single JSON object with exactly these fields. No markdown fences, \
no extra keys.

{
  "description": "<Prose narrative from beginning to end. Cover setting, \
subjects, actions, dialogue or voiceover, visual style (color, lighting, \
camera work, editing rhythm), and pacing. Present tense. Minimum 3 sentences.>",

  "key_subjects": [
    ["<name>", "<one sentence: who/what this is and their role in the video>"]
  ],

  "tone": ["<3–8 adjectives describing emotional register and stylistic feel, \
e.g. intimate, frenetic, melancholic>"],

  "genre_or_type": "<one word or compound (underscores allowed) reflecting the \
video's primary intent, e.g. documentary, commercial, tutorial, music_video>",

  "tags": ["<5–10 lowercase keywords covering subject, genre, mood, and \
distinctive visual or audio elements>"]
}
"""

SEGMENT_ANALYSIS_PROMPT = """\
You are a Professional Video Editor and Colorist performing a detailed analysis \
of a single scene extracted from a larger video.

### Global context
The following is a high-level summary of the full video this scene belongs to,
together with the splitting of the video in segments. \
Use this to understand narrative and stylistic context, but focus your analysis \
on what is visible in *this* clip.

<global_context>
Global Summary: {global_summary}

Segments: {segments}
</global_context>

### Segment info
- **Segment ID:** {segment_id}

### Output format
Return strictly valid JSON as a single-element array. No prose, no markdown fences.

[
  {{
    "segment_id": <string matching the one given>,
    "description": "Narrative summary following the pattern: [Subject] [Action] in [Environment]. E.g. 'Medium shot of a hiker reaching the summit during golden hour.'",
    "technical_specs": {{
      "framing": "One of: Extreme Wide Shot | Wide Shot | Medium Shot | Medium Close-Up | Close-Up | Extreme Close-Up | Over-the-Shoulder | POV Shot",
      "movement": "One of: Static | Pan Left | Pan Right | Tilt Up | Tilt Down | Dolly In | Dolly Out | Truck Left | Truck Right | Tracking Shot | Zoom In | Zoom Out | Arc Shot | Fly-By | Dolly Zoom",
      "angle": "One of: Eye Level | High Angle | Low Angle | Dutch Angle | Bird's Eye View | Worm's Eye View",
      "reasoning": {{
        "framing": "Why this framing was chosen.",
        "movement": "Why this camera movement was identified.",
        "angle": "Why this angle was identified."
      }}
    }},
    "color_profile": {{
      "dominant_colors": ["#RRGGBB"],
      "lighting_type": "E.g. Natural/Golden Hour | Harsh Midday | Overcast | Low-light/Interior | Neon/Stylized",
      "temperature": "One of: warm | cool | neutral"
    }},
    "highlights": [
      {{
        "description": "Specific micro-moment of visual or narrative interest.",
        "keywords": ["max 5 tags"],
        "start": "HH:MM:SS.mmm",
        "end": "HH:MM:SS.mmm"
      }}
    ],
    "quality_score": {{
      "rating": "One of: excellent | good | medium | bad",
      "reasoning": "Brief evaluation of aesthetic and cinematographic quality."
    }},
    "segment_tags": ["max 7 keywords describing the segment"]
  }}
]

### Example

[
  {{
    "segment_id": 1,
    "description": "Aerial bird's-eye view of a turquoise alpine lake surrounded by jagged limestone peaks. A small red boat is centred, creating a focal point against the water.",
    "technical_specs": {{
      "framing": "Wide Shot",
      "movement": "Dolly In",
      "angle": "Bird's Eye View",
      "reasoning": {{
        "framing": "The frame captures the full lake and surrounding peaks, emphasising scale and environment.",
        "movement": "The camera descends steadily toward the boat, increasing its visual weight over time.",
        "angle": "Near-vertical perspective flattens the segment into a map-like composition with minimal depth."
      }}
    }},
    "color_profile": {{
      "dominant_colors": ["#40E0D0", "#A9A9A9", "#FF0000"],
      "lighting_type": "Harsh Midday",
      "temperature": "neutral"
    }},
    "highlights": [
      {{
        "description": "Sunlight reflects sharply off the boat's hull, creating a specular highlight that anchors the eye.",
        "keywords": ["reflection", "specular", "focal point", "boat", "sunlight"],
        "start": "00:00:02.350",
        "end": "00:00:07.850"
      }}
    ],
    "quality_score": {{
      "rating": "excellent",
      "reasoning": "High dynamic range rendered cleanly; smooth gimbal movement delivers a professional cinematic feel with no visible compression artifacts."
    }},
    "segment_tags": ["alpine", "lake", "drone", "aerial", "nature", "turquoise", "serene"]
  }}
]
"""

STORY_WRITING_PROMPT = """\
You are a creative screenwriter. Based on the user's \
brief and the video descriptions provided as context, write an \
engaging, compelling story that captures the user's intent and covers \
the given video descriptions. This story serves as the blueprint for \
editing the available footage in a later step.

### User brief
{user_brief}

### Video context
The following descriptions come from the analysed video segments. Use them \
as the factual backbone of your story — the characters, settings, actions, \
and atmosphere they contain should inform your narrative.

<video_context>
{video_descriptions}
</video_context>

### Instructions
- Write in a vivid, immersive style.
- Adapt tone and genre to the footage.
- Evaluate carefully the available footage descriptions and create a compelling \
story arc, ordering the content as you find suitable.
- Ensure your story covers most of the video footage.
- Feel free to use sensory language and emotional depth.
- Do not invent facts that clearly contradict the video descriptions.
- Length: aim for 200-500 words, scaled to the complexity of the footage.

Return free-form prose only. No JSON, no headings, no bullet points.
"""

NARRATION_PROMPT = """\
You are a professional script editor specialising in narration. \
You will receive a creative story written for a video, and your task is to \
adapt it into a series of concise narration scenes that will be used to \
retrieve video segments and arrange them semantically to create an edit timeline \
matching your narration.

### Story
{story}

### Instructions
- Break the story into natural narration beats. Each segment should map to \
a distinct visual moment or emotional shift in the video.
- Preserve the tone and arc of the original story.
- Number segments sequentially starting from 1.

Return strictly valid JSON. No markdown fences, no prose outside the object.

{{
  "narration_segments": [
    {{
      "id": 1,
      "text": "<narration text for this segment>"
    }}
  ]
}}
"""

STORYBOARD_PROMPT = """
You are a professional movie director. \
You will receive a list of narration segments from your screenwriter and your task is to \
create a storyboard out of it. For this, create detailed scene descriptions from these narration segments. \
This storyboard will be used to create the editing script, which will \
retrieve video segments and arrange them semantically to create an edit timeline \
matching the storyboard.

### Narration Segments
{narration_segments}

### Video context
The following descriptions come from the analysed video segments. Use them \
to align your scene descriptions with the available content.

<video_context>
{video_descriptions}
</video_context>

### Instructions
- In the scene descriptions, use descriptive language useful for matching with video descriptions semantically.
- Preserve the tone and arc of the original story.
- Number scenes sequentially starting from 1.

Return strictly valid JSON. No markdown fences, no prose outside the object.

{{
  "scenes": [
{{
      "id": 1,
      "narration_segment": "<Segment of the original story serving as content anchor>"
      "scene_description": "<narration text for this segment>"
      "reasoning": "<short reasoning about the range of the chosen segment and the crafted scene>"
      "keywords": [List of max 7 keywords describing the scene]
}}
  ]
}}
"""
