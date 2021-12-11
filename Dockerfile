FROM conda/miniconda3
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
RUN conda install -y -q -c conda-forge mamba
COPY ./ ./
RUN mamba install -y -q -c conda-forge -c anaconda python=3.7
RUN mamba install -y -q -c conda-forge -c anaconda --file requirements-conda.txt
RUN mamba install -y -q -c conda-forge -c anaconda git
RUN git clone --single-branch --branch develop https://github.com/Micromeda/pygenprop.git
RUN pip -q install ./pygenprop/
RUN chmod +x micromeda-server.py
ADD https://raw.githubusercontent.com/ebi-pf-team/genome-properties/master/flatfiles/genomeProperties.txt ./
CMD ./micromeda-server.py -d ./genomeProperties.txt
