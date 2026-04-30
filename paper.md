---
title: 'wikipediaGATN: A Python package to derive the global air transportation networks'
tags:
  - Python
  - transportation
  - global air transportation networks
authors:
  - name: Julien Arino
    orcid: 0000-0001-6409-5027
    equal-contrib: true
    affiliation: 1
  - name: Adriana-Stefania Ciupeanu
    orcid: 0000-0003-0833-2176
    equal-contrib: true
    affiliation: 1
affiliations:
 - name: University of Manitoba, Winnipeg, Manitoba, Canada
   index: 1
date: 29 April 2026
bibliography: paper.bib

---

# Summary

The global air transportation networks for both passengers and cargo play a crucial role in a wide variety of human activities and, consequently, in the many areas of research related to these activities: economics, epidemiology, geography, sociology, transport, etc.
This package scrapes Wikipedia data to build a snapshot of the architecture of the global air transportation networks for passenger and cargo flights.


# Statement of need

`wikipediaGATN` is a Python package for deriving the structure of the global air transportation networks (GATN) from information publicly available on Wikipedia.

In the field of epidemiology, earlier work [@KhanArinoHuRaposoEtAl:2009] demonstrated the potential of the GATN for explaining the spread of infectious diseases.
Many commercial entities (IATA, OAG, etc.) have comprehensive datasets detailing the structure and utilisation of the GATN.
However, these datasets are often prohibitively priced.

`wikipediaGATN` seeks a middle ground: while not providing any information about flight volumes, it mines the wikipedia API to infer the structure of the GATN from information available on Wikipedia.
An earlier version was used by the authors and collaborators during the early stages of the COVID-19 pandemic for producing daily summaries of the likely next ISO-3166-1 level places to report cases of COVID-19.
It was used in the preparation of a report [@ArinoPortetBajeuxCiupeanu:2020] and is being used in a scientific publications under preparation on the subject.

The data is also used in one of the author's Mathematics of Data Science course, where techniques of social network analysis are presented.
Other researchers working on topics touching on the GATN will benefit from the package.
This will also be of interest to instructors teaching graph or network theory.

# Methods

Airport information pages on Wikipedia are quite standardised.
There is typically an infobox that presents summary information about the airport (name, IATA and ICAO codes, city served, geographical coordinates).
Most airport pages also contain a table detailing airlines operating out of the airport and the destinations they serve, for both passenger and cargo flights.
This homogeneisation of resources means that it is reasonably easy to use web scraping tools to gather information.

Starting from a seed airport, the process gathers information on the airlines operating out of the airport and the Wikipedia links to served destinations. 
This is level 0 of the network.
Information on destinations from first degree connections out of the seed is then gathered, with those links followed again.
The process is repeated until no new airports are found.
At the time of writing and using Winnipeg (YWG) where the authors are based as the seed, the process reached level 9 with a little over 4,000 airports in the graph.

To complement the information, we run further sweeps by checking which active airports in the OurAirports dataset are not present in the Wikipedia-derived network but have Wikipedia pages.
This adds about 200 airports to the graph, so that at the time of writing, the network has 4,275 airports. 
Each airport is described by its name, IATA, ICAO and GPS codes, latitude and longitude coordinates, continent, country and one or two subcountry divisions (province, state, territory, etc.) as well as (most often) a link to the Wikipedia page for the city it serves.

In order not to overwhelm Wikipedia servers, rate limitation is used, so the process takes a few hours.
Data from [OurAirports](https://ourairports.com/data/) is used to validate and enrich the information obtained from Wikipedia.

The output is two sets of networks (for passenger and cargo flights) in four different formats, as well as several plotly visualisations of the networks.
The process is easily automated so that periodic updates can be produced; the project repository has data updated monthly.



# Acknowledgements

We acknowledge useful discussions with Stéphanie Portet (University of Manitoba). 
JA acknowledges years of fruitful collaboration with Kamran Khan, CEO of Bluedot.global, through whom he had access to much more extensive data, as well as support from the Public Health Agency of Canada, who also provided access to extensive data during the early stages of the COVID-19 pandemic.
AI (Claude and Gemini) was used to help with coding.

# References