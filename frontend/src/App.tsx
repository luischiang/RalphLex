import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import Nav from "./components/Nav";
import CaseDetail from "./pages/CaseDetail";
import CaseList from "./pages/CaseList";
import CaseSubmit from "./pages/CaseSubmit";
import Monitor from "./pages/Monitor";

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-page-enter">
      <Routes location={location}>
        <Route path="/" element={<CaseList />} />
        <Route path="/submit" element={<CaseSubmit />} />
        <Route path="/cases/:caseId" element={<CaseDetail />} />
        <Route path="/monitor" element={<Monitor />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Nav />
        <main className="mx-auto max-w-6xl px-4 py-8">
          <AnimatedRoutes />
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
