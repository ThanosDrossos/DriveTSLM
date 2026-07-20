# DEMO.md · video walkthrough

A single screen recording of the deployed application, around four minutes, unhurried.
Log in first so the recording opens on the Welcome view. The text below is written to be
spoken, not read out verbatim. Move at your own pace and let the interface carry the
detail that is already on screen. Stage directions are in italics.

---

### Opening · *Welcome view*

This is Claims Desk, the proof-of-concept for the thesis I am proposing to the lab. The
starting observation is a simple one. Insurers hold a detailed recording of how a vehicle
was moving during a crash, and they hold the written account of what supposedly happened,
and the two are almost never checked against each other. The question I wanted to explore
is how far a language model can go in closing that gap, under the condition that it is
never allowed to simply assert something.

So the system is built around a single constraint. The model does not read the raw signal
directly. It works through deterministic tools that compute quantities from the telemetry,
and every number it states has to point back to the tool result it came from. A validator
on the backend then checks each of those references. If the model claims a value the tools
never produced, that claim is marked as unsupported. Grounding here is not encouraged, it
is required and then verified.

Everything runs on real, public crash data, and nothing is trained. That last point
matters for the argument I come back to at the end.

### The data · *Event Explorer*

*Open Event Explorer.*

These are the events the system reasons over, from two quite different sources. One is
high-frequency inertial data from real crashes, the accelerometer and gyroscope streams a
telematics device produces. The other is investigator case data, where a written crash
summary is paired with the vehicle's own event-data-recorder download. The view shows the
raw channels and the simple threshold detections the agent has access to. I would stress
that these detections are deliberately basic. They are the instrument, not the
contribution.

### The core comparison · *Grounded Analysis*

*Select a crash event and run both arms.*

This is the centre of the work. The same model runs in two conditions. On one side it has
the tools and operates under the citation constraint I described. On the other it is given
a clean plot of the whole event and nothing more, which is a fair way to let a model read
a time series, not a weakened one.

As the agent runs you can watch it decide what to inspect, call the tools, and read the
results back. When it writes its conclusion, each quantitative statement is linked to the
tool call behind it, and you can see those links resolve. Green means the value is present
in the cited result. Red means it is not, and the system surfaces that rather than
hiding it.

The point of the contrast is not that one answer is longer or more confident. It is that
only one of them can be audited. The plot-reading model may be perfectly reasonable, but
there is no way to hold any single number it gives you to account. That asymmetry, at
identical model capability, is what the design is meant to expose.

### Cross-examining a narrative · *Claims Desk*

*Select the Toyota Camry pole impact and run the check.*

The second capability moves this closer to the eventual use case. The input now is an
accident narrative together with the telemetry. The system first breaks the narrative into
small, individually checkable claims, typed by what they concern, speed, braking,
direction, severity, and so on. It then verifies each one against the sensors and commits
to a verdict, supported, contradicted, or unverifiable, with the evidence attached.

Take this case. The account describes the pole impact as minor. The recorder says
otherwise, a severe frontal deceleration with the airbag firing almost immediately, so the
severity claim comes back contradicted, and you can read why. Notice also where the checker
abstains. Something like repair cost, or the driver's intention, is not decidable from
motion data, and the correct behavior there is to say so rather than guess.

Only after the verdict does the interface reveal the ground truth for the narrative, which
error was introduced, if any. That ordering is deliberate. Each narrative has a known
answer by construction, so the verdict can be scored rather than simply admired.

### The evaluation · *Results*

*Open Results.*

Because every narrative carries a constructed ground truth, the whole set can be run
repeatedly and scored without a human, and without a second model acting as judge. The
figures are on the screen, so I will leave them there. The finding I would draw out is
qualitative. Some kinds of misstatement, about speed or severity, are caught almost every
time. Others, in particular the direction an impact came from, are much harder, because the
sensor frame does not resolve them cleanly. Knowing which classes of error are detectable,
and under what conditions, is itself a result, and it is one of the questions the thesis is
built to answer.

### The research problem · *closing*

That is what exists today, and it is deliberately the version with no training in it. The
thesis develops each half.

The first line of work asks whether time-series language models, which this lab
established for medical signals, transfer to vehicle motion, and whether a trained model
can match specialized crash detectors while still producing an account of its reasoning
that can be audited, and at what cost. The second turns the consistency check you have
just seen into a proper benchmark, built from real narrative and recorder pairs with
controlled perturbations, so that the question I gestured at, which errors are detectable
and which are not, can be answered systematically.

The domain is not incidental. It sits on the lab's work on time-series language models and
on its insurance partnership, in a setting where an answer is only useful if it can be
audited. That is the thread running through the whole demonstration, and it is the reason
the grounding constraint, rather than the model itself, is the real subject.

---

*Practical notes: fresh session, type the password on camera; 1080p capture, bookmarks bar
hidden; pre-run one grounded analysis and the Camry check in background tabs in case live
latency is poor; end on the repository and hosted-demo URLs.*
