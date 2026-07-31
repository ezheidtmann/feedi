import feedi.scraping as scraping
from tests.conftest import mock_request

PARAGRAPH = (
    "I kicked off the extended train, over 6.4B unique tokens, using my JAX code "
    "because it is somewhat faster than the PyTorch version, and then waited for "
    "the loss curves to show up on the dashboard so I could compare them. "
)

# A post shaped like the ones a static site generator produces: a syntax highlighted
# code block wrapped in a div, and a plain list, both siblings of the paragraphs.
ARTICLE_HTML = f"""
<html>
  <head><title>Why do the weights beat mine?</title></head>
  <body>
    <div class="content">
      <h2>The extended-train model</h2>
      <p>{PARAGRAPH}</p>
      <p>Before running it, I decided to write down what I expected to see. I felt that:</p>
      <ul>
        <li>my first expectation was that both models would get better results on the
            test loss eval than my existing ones, at around 90% probability</li>
        <li>my second expectation was that both would still score worse than GPT-2
            small on the instruction following test</li>
      </ul>
      <p>It was time to find out! {PARAGRAPH}</p>
      <p>It crashed after about 40 hours, with this error:</p>
      <div class="codehilite">
<pre><span></span><code><span>jax.errors.JaxRuntimeError: INTERNAL: CUDA error: Failed to end stream capture</span>
</code></pre>
      </div>
      <p>There were no obvious issues with the machine. {PARAGRAPH}</p>
      <p>{PARAGRAPH}</p>
    </div>
  </body>
</html>
"""


def test_extract_keeps_code_blocks_and_lists(app):
    """
    Syntax highlighters wrap code blocks in a div, and readability drops divs it decides
    hold no useful content. It measures that with a tag selector spelled in uppercase,
    which only matches on a DOM that compares html tag names case insensitively (as
    browsers do). On one that doesn't, every div wrapped code block on the page is
    silently stripped, taking the code with it.
    """
    url = "http://example.com/an-article"
    mock_request(url, body=ARTICLE_HTML)

    with app.app_context():
        content = scraping.extract(url)["content"]

    assert "<pre" in content
    assert "jax.errors.JaxRuntimeError" in content

    assert "<ul>" in content
    assert "my first expectation" in content
    assert "my second expectation" in content


LAZY_IMAGE_HTML = f"""
<html>
  <head><title>A post with lazy loaded images</title></head>
  <body>
    <div class="content">
      <h2>A post with lazy loaded images</h2>
      <p>{PARAGRAPH}</p>
      <p><img src="data:image/gif;base64,placeholder" alt="a loss chart"
              data-srcset="http://example.com/chart-400.png 400w, http://example.com/chart-800.png 800w"/></p>
      <p>{PARAGRAPH}</p>
      <p><img src="data:image/gif;base64,placeholder" data-src="http://example.com/plot.png"/></p>
      <p>{PARAGRAPH}</p>
    </div>
  </body>
</html>
"""


def test_extract_resolves_lazy_loaded_images(app):
    "A srcset is a list of candidates, so it can't be dropped into src as it is."
    url = "http://example.com/lazy-images"
    mock_request(url, body=LAZY_IMAGE_HTML)

    with app.app_context():
        content = scraping.extract(url)["content"]

    assert 'src="http://example.com/chart-400.png"' in content
    assert 'alt="a loss chart"' in content
    assert "400w" not in content

    assert 'src="http://example.com/plot.png"' in content
