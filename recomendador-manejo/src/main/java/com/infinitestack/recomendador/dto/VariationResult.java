package com.infinitestack.recomendador.dto;

public class VariationResult {
    private String deVaried;
    private int mesPlantio;
    private int mesColheita;
    private int numeroDeMeses;
    private double rfPrediction;
    private double gbmPrediction;

    public String getDeVaried() { return deVaried; }
    public void setDeVaried(String deVaried) { this.deVaried = deVaried; }
    public int getMesPlantio() { return mesPlantio; }
    public void setMesPlantio(int mesPlantio) { this.mesPlantio = mesPlantio; }
    public int getMesColheita() { return mesColheita; }
    public void setMesColheita(int mesColheita) { this.mesColheita = mesColheita; }
    public int getNumeroDeMeses() { return numeroDeMeses; }
    public void setNumeroDeMeses(int numeroDeMeses) { this.numeroDeMeses = numeroDeMeses; }
    public double getRfPrediction() { return rfPrediction; }
    public void setRfPrediction(double rfPrediction) { this.rfPrediction = rfPrediction; }
    public double getGbmPrediction() { return gbmPrediction; }
    public void setGbmPrediction(double gbmPrediction) { this.gbmPrediction = gbmPrediction; }
}
