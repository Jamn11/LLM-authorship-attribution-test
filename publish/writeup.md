# Preliminary Findings on Author-Style Identification; or, Welcome to the Age of Truesight

I want to contribute some hard numbers to the authorship attribution discourse, first started by Kelsey Piper (CLAUDE: link to the Kelsey Piper article about this). I wanted to find out how many words a model actually needs in order to correctly ID an author. 

First, on the methodology. I did not use unpublished text, because I don't have access to any that is written by someone famous enought to plausibly be ID'
ed. Instead, I used text sources that came out after the models I tested released. This guarantees that the models are doing attribution through style-matching rather than by memorizing who wrote a given snippet of text. Second, my test-set here is necessarily somewhat limited just because I didn't want to burn too many API tokens. For that reason, you should take this data as really quite noisy. Still, I think what I have done here is a decent basis on which to establish an OOM understanding of how much text LLMs need to ID. If you know someone with excess API credits and want to see a more full test set, be sure to reach out! Third, my tests ended up mostly being based on Zvi's article about the Opus 4.8 model card (CLAUDE: please link). This was more contingent-than-reasoned-decision, stemming from the fact that I became interested in answering this question while reading that piece. This may have confounded the numbers since model card review is already very Zvi-coded. Claude may have been picking up more on the subject than the style. Again, more work to be done here. 

The two metrics I focused on were "text-to-50%" and "text-to-80%". They show the snippet-length the model needed on average in order to correctly ID an author with 50 or 80 percent accuracy, respectively. Without further ado, the table:

(CLAUDE: put table_models_zvi.png here)

All of these numbers are runs of different models on the Zvi-review corpus. The actual test was: split the article into sentences and paragraphs, ask the model to ID them, count accuracy. I then calculated the accuracy numbers using word count, both on the paragraphs and sentences. 

A few things that stand out here:
1. The SOTA models need *strikingly* few words to ID Zvi. Just 18 words gets you above 50% accuracy. This plausibly gets you into short-tweet range. I also suspect this is pretty darn close to the theoretical ceiling of how much information you can squeeze out of an isolated snippet of text. 
2. There is a clear trend of improvement over time. Opus 4.8 > Opus 4.5 > Sonnet 4.0. There is plausibly a bigger is better effect too, however, since the older Opus 4.5 is either a tiny bit better than, or at least as good as, the newer Sonnet 4.6
3. DeepSeek is *really* bad. Flash is no better than random, and Pro trails even Sonnet 4.0. Speculating here, but I wonder if this capability is really hard to distill for some reason. Or maybe DeepSeek just isn't trying to distill it? By all other benchmarks, V4 pro should be a *much* better model than Sonnet 4.
4. GPT-5.5 is SOTA. I think there is something of a "Claude has truesight but GPT doesn't" narrative, and this result clearly violates that. 5.5 is as good as, if not better than, Opus at identifying Zvi. That being said, it was roughly five-times more expensive to run than Opus, mostly driven by spending more tokens thinking. I ran Opus on high and 5.5 on medium.

In addition to asking for an author guess, I asked for confidence estimates. Opus, 5.5, and Sonnet 4.6, all seemed to "know when they knew". If anything, they were significantly under-estimating proper confidence levels. 

(Claude: add calibration_by_model.png)

Identifying Zvi from a post reviewing an AI model seems to be basically ideal conditions for the models. Probably this is because the number of people who review AI model system cards is genuinely small and because Zvi is a prolific writer with a distinct voice. Also, he is in the LessWrong world that Claude, and people working at Anthropic, probably over-index on. For that reason, I tested Opus 4.8 on a few other authors with the same method:

(CLAUDE: add table_opus48_by_author.png)

The only author more-easily identified than Zvi was Simon Willison, though his snippet was the shortest of the bunch and was also in the rather small world of AI-model reviewers. Identification gets harder as the author gets less well-known and further from LessWrong. Still, the 50% marker for all of them is less than 100 words, and the 80% marker for all but Gruber is under 103 words.

I'll end with some thoughts, speculations, and predictions. First, this is obviously a wildly superhuman ability of the models. I doubt anyone completely unaided by tools or web search could reach this level of accuracy. Second, it's not clear that that's surprising. These models only know text (basically), so it makes sense that they would end up with a deep, intimate understanding of the nuances of text. Third, as others have already pointed out, this could be a big problem for anonymous writers. What is novel here, I think, is that it shows that the minimum-identifying-snippet could be insanely short. The end run of this type of capability could be something really close to actual truesight: models that you cannot lie to. I don't think we're there yet, but maybe we have line of sight? Perhaps an idea for an extension of this experiment would be to test how accurately AI models can detect that a user is lying. 

I am stopping here because I want to get this post up, but to say it once more, there is plenty more work to be done in making this rigorous. I have linked our to a repo with the pipeline for scraping and testing I used to collect this data, as well as the full data set. I stripped out the actual text snippets since they are copyrighted, and I didn't want to post other peoples' articles on a Github repo without permission.
