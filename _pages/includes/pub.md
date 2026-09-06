<section id="publications" aria-labelledby="publications-heading">
  <div class="section-heading">
    <h2 id="publications-heading">Publications</h2>
  </div>
  <time data-scholar-updated datetime="{{ site.data.scholar_stats.updated }}" hidden></time>
  {% assign selected_papers = site.data.publications | where: "selected", true %}
  {% for paper in selected_papers %}
    {% include publication.html paper=paper featured=true %}
  {% endfor %}
  {% assign other_papers = site.data.publications | where: "selected", false %}
  <details class="more-publications">
    <summary>More publications <span class="publication-count">{{ other_papers.size }}</span></summary>
    <div class="publication-list">
      {% for paper in other_papers %}
        {% include publication.html paper=paper featured=false %}
      {% endfor %}
    </div>
  </details>
</section>
