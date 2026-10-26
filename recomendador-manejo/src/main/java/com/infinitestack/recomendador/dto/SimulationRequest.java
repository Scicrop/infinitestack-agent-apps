package com.infinitestack.recomendador.dto;

public class SimulationRequest {
    private String deVaried;
    private Integer cdEstagio;
    private Integer mesPlantio;
    private Integer numeroDeMeses;
    private Integer cdAmbienteProd;

    public String getDeVaried() { return deVaried; }
    public void setDeVaried(String deVaried) { this.deVaried = deVaried; }
    public Integer getCdEstagio() { return cdEstagio; }
    public void setCdEstagio(Integer cdEstagio) { this.cdEstagio = cdEstagio; }
    public Integer getMesPlantio() { return mesPlantio; }
    public void setMesPlantio(Integer mesPlantio) { this.mesPlantio = mesPlantio; }
    public Integer getNumeroDeMeses() { return numeroDeMeses; }
    public void setNumeroDeMeses(Integer numeroDeMeses) { this.numeroDeMeses = numeroDeMeses; }
    public Integer getCdAmbienteProd() { return cdAmbienteProd; }
    public void setCdAmbienteProd(Integer cdAmbienteProd) { this.cdAmbienteProd = cdAmbienteProd; }
}
